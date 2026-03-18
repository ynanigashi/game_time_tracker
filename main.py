"""Game Time Tracker - PySide6 GUI."""

import atexit
import ctypes
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, TypeVar, cast

# ロギング設定
_file_handler = logging.FileHandler('game_time_tracker.log', encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        _file_handler,
    ]
)
atexit.register(logging.shutdown)
logger = logging.getLogger(__name__)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidgetItem, QVBoxLayout, QWidget

from config_loader import DEFAULT_BROWSERS, DEFAULT_EXCLUDED_TITLES, ConfigLoader, Config
from gui_layout import LayoutWidgets, build_main_layout
from log_handler import LogHandler
from models import GameEntry
from services import (
    DailyStatsTracker,
    GameInfoLoader,
    ScanResult,
    GameStateTracker,
    Messages,
    SessionRecorder,
    WindowScanner,
    MIN_PLAY_MINUTES,
)
from time_utils import SECONDS_PER_MINUTE, calc_today_elapsed_seconds, format_hms
from window_state import (
    DEFAULT_OVERTIME_ALERT_ENABLED,
    DISPLAY_MODES,
    MODE_DEFAULT_SIZES,
    WindowState,
)


# =============================================================================
# 定数
# =============================================================================
POLL_INTERVAL_SECONDS = 1
INACTIVE_TIMEOUT_MINUTES = 5  # 非アクティブ状態でこの時間経過でセッション分割
STATE_FILE = Path("window_state.txt")
BASE_TITLE = "Game Time Tracker"
UI_REFRESH_INTERVAL_SECONDS = 0.1
MAX_WIDGET_HEIGHT = 16777215  # Qt default max height
OVERLAY_FALLBACK_WIDTH = 240
OVERLAY_FALLBACK_HEIGHT = 40
MAX_Z_WALK = 32
MIN_MODE_SAFE_WIDTH = 320
MIN_MODE_SAFE_HEIGHT = 110
OVERLAY_SAMPLE_RATIOS: Tuple[Tuple[float, float], ...] = (
    (0.5, 0.5),
    (0.25, 0.25),
    (0.75, 0.25),
    (0.25, 0.75),
    (0.75, 0.75),
)
OVERTIME_ALERT_THRESHOLDS_MINUTES: Tuple[int, ...] = (45, 50, 55, 58, 60)
TDependency = TypeVar("TDependency")
Point = Tuple[int, int]
Rect = Tuple[int, int, int, int]

_USER32 = ctypes.windll.user32 if sys.platform == "win32" else None


@dataclass
class OvertimeAlertTracker:
    """時間超過防止アラートの進捗状態を管理する。"""

    thresholds_minutes: Tuple[int, ...]
    alerted_threshold_minutes: set[int]
    last_checked_seconds: float = 0.0
    initialized: bool = False

    def prime(self, total_seconds: float) -> None:
        """現在値を基準に進捗を初期化し、遡及通知を抑止する。"""
        self.last_checked_seconds = max(0.0, float(total_seconds))
        self.alerted_threshold_minutes = {
            minute
            for minute in self.thresholds_minutes
            if self.last_checked_seconds >= minute * SECONDS_PER_MINUTE
        }
        self.initialized = True

    def update(self, total_seconds: float, *, alerts_enabled: bool) -> List[int]:
        """閾値跨ぎを更新し、今回通知すべき閾値（分）を返す。"""
        if not self.initialized:
            self.prime(total_seconds)
            return []

        previous_seconds = self.last_checked_seconds
        current_seconds = max(0.0, float(total_seconds))
        self.last_checked_seconds = current_seconds

        if not alerts_enabled:
            return []

        triggered: List[int] = []
        for minute in self.thresholds_minutes:
            if minute in self.alerted_threshold_minutes:
                continue
            threshold_seconds = minute * SECONDS_PER_MINUTE
            if previous_seconds < threshold_seconds <= current_seconds:
                self.alerted_threshold_minutes.add(minute)
                triggered.append(minute)
        return triggered


def clamp_mode_size(display_mode: str, width: int, height: int) -> Tuple[int, int]:
    """表示モードごとの最低サイズを保証する。"""
    if display_mode == "min":
        return max(width, MIN_MODE_SAFE_WIDTH), max(height, MIN_MODE_SAFE_HEIGHT)
    return width, height


class _WinPoint(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class _WinRect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


if _USER32 is not None:
    _USER32.GetForegroundWindow.restype = ctypes.c_void_p
    _USER32.GetWindow.restype = ctypes.c_void_p
    _USER32.GetAncestor.restype = ctypes.c_void_p
    _USER32.WindowFromPoint.restype = ctypes.c_void_p
    _USER32.GetWindowRect.restype = ctypes.c_int
    _USER32.GetWindowThreadProcessId.restype = ctypes.c_uint


class TodayTimeOverlayWindow(QWidget):
    """フルスクリーンゲーム中に表示する、今日の時間専用オーバーレイ."""

    def __init__(self) -> None:
        super().__init__()
        self._time_display = QLabel("00:00:00.0", self)
        self._configure_window()
        self._build_layout()
        self.resize(OVERLAY_FALLBACK_WIDTH, OVERLAY_FALLBACK_HEIGHT)

    @staticmethod
    def _window_flag(flag_name: str) -> object:
        window_type = getattr(Qt, "WindowType", None)
        if window_type is not None and hasattr(window_type, flag_name):
            return getattr(window_type, flag_name)
        return getattr(Qt, flag_name, 0)

    @staticmethod
    def _widget_attribute(attribute_name: str) -> Optional[object]:
        widget_attribute = getattr(Qt, "WidgetAttribute", None)
        if widget_attribute is not None and hasattr(widget_attribute, attribute_name):
            return getattr(widget_attribute, attribute_name)
        return getattr(Qt, attribute_name, None)

    def _set_widget_attribute(self, attribute_name: str, enabled: bool = True) -> None:
        attribute = self._widget_attribute(attribute_name)
        if attribute is not None:
            self.setAttribute(attribute, enabled)

    def _configure_window(self) -> None:
        flags = (
            self._window_flag("Tool")
            | self._window_flag("FramelessWindowHint")
            | self._window_flag("WindowStaysOnTopHint")
            | self._window_flag("WindowTransparentForInput")
        )
        self.setWindowFlags(flags)
        self.setWindowOpacity(0.88)

        self._set_widget_attribute("WA_TranslucentBackground")
        self._set_widget_attribute("WA_ShowWithoutActivating")
        self._set_widget_attribute("WA_TransparentForMouseEvents")

        focus_policy_enum = getattr(Qt, "FocusPolicy", None)
        no_focus_policy = (
            getattr(focus_policy_enum, "NoFocus", None)
            if focus_policy_enum is not None
            else None
        )
        if no_focus_policy is not None:
            self.setFocusPolicy(no_focus_policy)

    def _build_layout(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self._time_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_display.setStyleSheet(
            "QLabel {"
            "  background-color: rgba(15, 15, 15, 190);"
            "  color: #FFFFFF;"
            "  border-radius: 8px;"
            "  font-size: 20px;"
            "  font-weight: bold;"
            "  padding: 2px 6px;"
            "}"
        )
        layout.addWidget(self._time_display)
        self.setLayout(layout)

    def set_today_text(self, formatted_time: str) -> None:
        self._time_display.setText(formatted_time)


class MainWindowUiController:
    """MainWindow の UI 更新専用ロジック."""

    def __init__(self, widgets: LayoutWidgets, daily_stats: DailyStatsTracker) -> None:
        self.w = widgets
        self.daily_stats = daily_stats

    @staticmethod
    def all_playing_games(
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> List[GameEntry]:
        """アクティブ/非アクティブを統合したプレイ中ゲーム一覧を返す."""
        return list(active_games) + list(inactive_games)

    def update_active_list(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> None:
        """プレイ中ゲームリストを更新."""
        if not active_games and not inactive_games:
            self.w.active_display.setText('---')
            return

        parts = [game.game_title for game in active_games]
        parts.extend(f'{game.game_title} - 停止中' for game in inactive_games)
        self.w.active_display.setText(' / '.join(parts))

    def update_session_times(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> None:
        """現在のセッション時間を更新（最長セッションを表示）。"""
        all_playing = self.all_playing_games(active_games, inactive_games)
        if not all_playing:
            self.w.session_time_display.setText('---')
            return

        max_elapsed = max(
            (now - game.start_time).total_seconds()
            if game.start_time else 0
            for game in all_playing
        )
        self.w.session_time_display.setText(format_hms(max_elapsed))

    def calculate_today_total_seconds(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> float:
        """今日のプレイ時間（完了+進行中）秒数を計算する。"""
        total_seconds = self.daily_stats.today_completed_seconds
        min_seconds = MIN_PLAY_MINUTES * SECONDS_PER_MINUTE

        all_playing = self.all_playing_games(active_games, inactive_games)
        for game in all_playing:
            if game.start_time:
                elapsed_seconds = calc_today_elapsed_seconds(game.start_time, now)
                if elapsed_seconds >= min_seconds:
                    total_seconds += elapsed_seconds
        return total_seconds

    def update_today_totals(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> float:
        """今日のプレイ時間（完了+進行中）を更新."""
        total_seconds = self.calculate_today_total_seconds(active_games, inactive_games, now)
        self.w.today_time_display.setText(format_hms(total_seconds))
        return total_seconds

    def update_window_list(self, window_titles: Sequence[str]) -> None:
        """現在のウィンドウタイトルリストを更新."""
        self.w.window_list.clear()
        for title in window_titles:
            self.w.window_list.addItem(title)

    def update_today_games_list(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> None:
        """今日プレイしたゲームの一覧と時間を更新."""
        game_minutes = dict(self.daily_stats.today_game_minutes_cache)
        all_playing = self.all_playing_games(active_games, inactive_games)

        if not game_minutes and not all_playing:
            if self.daily_stats.last_today_games_content != "":
                self.daily_stats.last_today_games_content = ""
                self.w.today_games_table.setRowCount(0)
            return

        for game in all_playing:
            current_minutes = (
                calc_today_elapsed_seconds(game.start_time, now) / SECONDS_PER_MINUTE
                if game.start_time else 0.0
            )
            if current_minutes >= MIN_PLAY_MINUTES:
                game_minutes[game.game_title] = game_minutes.get(game.game_title, 0) + current_minutes

        sorted_games = sorted(game_minutes.items(), key=lambda x: x[1], reverse=True)
        content = '\n'.join(f'{game_title}: {int(minutes)}分' for game_title, minutes in sorted_games)

        if content != self.daily_stats.last_today_games_content:
            self.daily_stats.last_today_games_content = content
            self.w.today_games_table.setRowCount(len(sorted_games))
            for row, (game_title, minutes) in enumerate(sorted_games):
                self.w.today_games_table.setItem(row, 0, QTableWidgetItem(game_title))
                self.w.today_games_table.setItem(row, 1, QTableWidgetItem(f'{int(minutes)}分'))


class MainWindowDisplayController:
    """MainWindow の表示モード制御ロジック."""

    def __init__(self, max_widget_height: int) -> None:
        self.max_widget_height = max_widget_height

    def set_widget_visibility(self, widget: QWidget, visible: bool) -> None:
        """ウィジェットの表示/非表示を設定."""
        widget.setVisible(visible)

    def set_widget_with_height(
        self,
        widget: QWidget,
        visible: bool,
        *,
        min_height: int,
        max_height: int,
    ) -> None:
        """ウィジェットの表示/非表示と高さ制約を設定."""
        widget.setVisible(visible)
        widget.setMinimumHeight(min_height)
        widget.setMaximumHeight(max_height)

    def apply_mode_geometry(
        self,
        window: QWidget,
        display_mode: str,
        mode_sizes: Dict[str, Tuple[int, int]],
    ) -> None:
        """表示モードに応じたサイズを適用."""
        w, h = mode_sizes.get(display_mode, MODE_DEFAULT_SIZES[display_mode])
        w, h = clamp_mode_size(display_mode, int(w), int(h))
        mode_sizes[display_mode] = (w, h)
        # サイズを強制適用するため、一時的に min/max を固定
        window.setMinimumHeight(h)
        window.setMaximumHeight(h)
        window.resize(w, h)
        window.setMinimumHeight(0)
        window.setMaximumHeight(self.max_widget_height)

    def apply_display_mode(
        self,
        *,
        display_mode: str,
        widgets: LayoutWidgets,
        set_widget_visibility: Callable[[QWidget, bool], None],
        set_widget_with_height: Callable[..., None],
        apply_mode_geometry: Callable[[], None],
    ) -> None:
        """表示モードに応じてウィジェット表示を切り替え."""
        is_expanded = display_mode != "min"  # mid/maxで表示
        is_max = display_mode == "max"

        # minではラベルを隠して時間表示領域を優先
        set_widget_visibility(widgets.today_label, is_expanded)
        set_widget_visibility(widgets.today_time_display, True)

        # mid/maxで表示
        set_widget_visibility(widgets.session_label, is_expanded)
        set_widget_with_height(
            widgets.session_time_display,
            is_expanded,
            min_height=0,
            max_height=self.max_widget_height if is_expanded else 0,
        )

        set_widget_visibility(widgets.active_label, is_expanded)
        set_widget_with_height(
            widgets.active_display,
            is_expanded,
            min_height=widgets.active_min_height if is_expanded else 0,
            max_height=widgets.active_max_height if is_expanded else 0,
        )

        set_widget_visibility(widgets.today_games_label, is_expanded)
        set_widget_with_height(
            widgets.today_games_table,
            is_expanded,
            min_height=widgets.today_games_min_height if is_expanded else 0,
            max_height=self.max_widget_height if is_expanded else 0,
        )

        # maxのみ表示
        set_widget_visibility(widgets.window_label, is_max)
        set_widget_with_height(
            widgets.window_list,
            is_max,
            min_height=0,
            max_height=self.max_widget_height if is_max else 0,
        )

        if widgets.overtime_alert_toggle is not None:
            set_widget_visibility(widgets.overtime_alert_toggle, True)

        apply_mode_geometry()

    def next_display_mode(self, current_display_mode: str) -> str:
        """現在の表示モードから次のモードを返す."""
        idx = DISPLAY_MODES.index(current_display_mode)
        return DISPLAY_MODES[(idx + 1) % len(DISPLAY_MODES)]


class MainWindowStateController:
    """MainWindow の状態読み書きロジック."""

    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file

    def load_all(self) -> Tuple[int, int, str, Dict[str, Tuple[int, int]], bool]:
        """永続化されたウィンドウ状態と設定を読み込む."""
        return WindowState.load_all(self.state_file)

    def load(self) -> Tuple[int, int, str, Dict[str, Tuple[int, int]]]:
        """永続化されたウィンドウ状態を読み込む."""
        x, y, mode, mode_sizes, _ = self.load_all()
        return x, y, mode, mode_sizes

    def load_overtime_alert_enabled(self) -> bool:
        """時間超過防止アラート設定を読み込む."""
        _, _, _, _, overtime_alert_enabled = self.load_all()
        return overtime_alert_enabled

    def save(
        self,
        geom: object,
        display_mode: str,
        mode_sizes: Dict[str, Tuple[int, int]],
        overtime_alert_enabled: bool,
    ) -> None:
        """現在状態を mode_sizes に反映して永続化."""
        mode_sizes[display_mode] = clamp_mode_size(
            display_mode,
            int(geom.width()),
            int(geom.height()),
        )
        WindowState.save(
            self.state_file,
            geom.x(),
            geom.y(),
            display_mode,
            mode_sizes,
            overtime_alert_enabled=bool(overtime_alert_enabled),
        )

    @staticmethod
    def record_resize(
        mode_sizes: Dict[str, Tuple[int, int]],
        display_mode: str,
        width: int,
        height: int,
    ) -> None:
        """リサイズ後サイズを mode_sizes に反映."""
        mode_sizes[display_mode] = clamp_mode_size(
            display_mode,
            int(width),
            int(height),
        )


class MainWindowLoopController:
    """MainWindow のタイマー起動と tick オーケストレーション."""

    def start_timer(
        self,
        owner: QWidget,
        interval_seconds: float,
        callback: Callable[[], None],
    ) -> QTimer:
        """タイマーを作成して開始."""
        timer = QTimer(owner)
        timer.setInterval(int(interval_seconds * 1000))
        timer.timeout.connect(callback)
        timer.start()
        return timer

    def run_scan_tick(self, window: "MainWindow") -> None:
        """監視サイクル（1秒間隔）."""
        if not window.games:
            return

        if window.daily_stats.check_day_change():
            # 日付変更時、UIも強制クリア
            window.w.today_games_table.setRowCount(0)
            window._prime_overtime_alert_progress(0.0)

        window_titles = window.scanner.get_titles()
        foreground_title = window.scanner.get_foreground_title()
        result = window._scan_games(window_titles, foreground_title)
        window._apply_scan_result(window_titles, result)

    def run_ui_tick(self, window: "MainWindow") -> None:
        """UIだけを高速更新（0.1秒間隔）."""
        now = datetime.now()
        # セッション時間と今日の合計時間のみ更新（リストはスキャン時に更新）
        window._update_session_times(window.active_games_cache, now)
        total_seconds = window._update_today_totals(window.active_games_cache, now)
        window._update_today_games_list(now)
        window._update_overtime_alert(total_seconds)


class MainWindowOverlayController:
    """MainWindow のオーバーレイ表示制御ロジック."""

    def __init__(self, owner: "MainWindow") -> None:
        self.owner = owner

    def initialize_overlay(self) -> None:
        """今日のプレイ時間オーバーレイを初期化する."""
        if self.owner._get_overlay_window() is not None:
            return

        try:
            self.owner.overlay_window = TodayTimeOverlayWindow()
            self.owner.overlay_window.hide()
            self.sync_overlay()
        except Exception as e:
            logger.warning(f"オーバーレイ初期化に失敗したため無効化します: {e}")
            self.owner.overlay_window = None

    def refresh_overlay_time(self) -> None:
        """オーバーレイの時刻表示を更新する."""
        overlay_window = self.owner._get_overlay_window()
        today_time_display = self.owner._get_today_time_display()
        if overlay_window is None or today_time_display is None:
            return
        overlay_window.set_today_text(today_time_display.text())

    def sync_overlay_geometry(self) -> None:
        """オーバーレイを today_time_display の位置とサイズに追従させる."""
        overlay_window = self.owner._get_overlay_window()
        target = self.owner._get_today_time_display()
        if overlay_window is None or target is None:
            return

        try:
            top_left = target.mapToGlobal(target.rect().topLeft())
            width = max(1, int(target.width()))
            height = max(1, int(target.height()))
            overlay_window.setGeometry(top_left.x(), top_left.y(), width, height)
        except Exception:
            return

    def should_show_overlay(self) -> bool:
        """メインウィンドウ背面かつtoday表示部が重なっている時のみ表示."""
        if not self.owner._is_overtime_alert_enabled():
            return False

        is_minimized = getattr(self.owner, "isMinimized", lambda: False)()
        is_visible = getattr(self.owner, "isVisible", lambda: True)()
        is_active = getattr(self.owner, "isActiveWindow", lambda: False)()
        if is_minimized or not is_visible:
            return False
        if is_active:
            return False
        return self.owner._is_today_display_covered_by_foreground_window()

    def sync_overlay_visibility(self) -> None:
        """表示条件に応じてオーバーレイを表示/非表示する."""
        overlay_window = self.owner._get_overlay_window()
        if overlay_window is None:
            return

        # オーバーレイ自身をヒットテスト対象から外して被覆判定する。
        was_visible = bool(getattr(overlay_window, "isVisible", lambda: False)())
        if was_visible:
            overlay_window.hide()

        if self.owner._should_show_overlay():
            overlay_window.show()
        else:
            overlay_window.hide()

    def sync_overlay(self) -> None:
        """オーバーレイの表示内容・位置・可視状態を同期する."""
        if not self.owner._is_overtime_alert_enabled():
            overlay_window = self.owner._get_overlay_window()
            if overlay_window is not None:
                overlay_window.hide()
            return

        self.refresh_overlay_time()
        self.sync_overlay_geometry()
        self.sync_overlay_visibility()

    def close_overlay(self) -> None:
        """オーバーレイを閉じて参照を解放する."""
        overlay_window = self.owner._get_overlay_window()
        if overlay_window is None:
            return
        overlay_window.close()
        self.owner.overlay_window = None


class NoGamesConfiguredError(Exception):
    """ゲーム情報が1件も読み込めなかったことを示す例外."""


@dataclass
class MainWindowBootstrapResult:
    """MainWindow の初期化に必要な依存と初期データ."""

    games: List[GameEntry]
    browsers: Sequence[str]
    scanner: WindowScanner
    recorder: SessionRecorder
    state_tracker: GameStateTracker
    today_game_minutes: Dict[str, float]
    today_completed_seconds: float


class MainWindowBootstrapError(Exception):
    """MainWindow 初期化でユーザー向けに扱う例外."""

    def __init__(self, status_message: str, log_message: Optional[str] = None) -> None:
        super().__init__(status_message)
        self.status_message = status_message
        self.log_message = log_message


class MainWindowBootstrapper:
    """MainWindow の依存構築・初期データ読み込みを担当."""

    def __init__(
        self,
        *,
        base_title: str,
        min_play_minutes: int,
        inactive_timeout_minutes: int,
        daily_stats: DailyStatsTracker,
    ) -> None:
        self.base_title = base_title
        self.min_play_minutes = min_play_minutes
        self.inactive_timeout_minutes = inactive_timeout_minutes
        self.daily_stats = daily_stats

    def bootstrap(self, *, window_title: str) -> MainWindowBootstrapResult:
        """設定・サービス・初期統計をまとめて構築する."""
        try:
            config = ConfigLoader().load()
            games = GameInfoLoader(config).load()
            if not games:
                raise NoGamesConfiguredError

            browsers = config.window_scan.browsers
            scanner = WindowScanner(
                excluded_titles=(
                    list(config.window_scan.excluded_titles)
                    + [self.base_title, window_title]
                )
            )

            log_handler = LogHandler(config.log_handler)
            recorder = SessionRecorder(
                log_handler=log_handler,
                min_play_minutes=self.min_play_minutes,
            )
            state_tracker = GameStateTracker(
                recorder=recorder,
                daily_stats=self.daily_stats,
                browsers=list(browsers),
                inactive_timeout_minutes=self.inactive_timeout_minutes,
            )
            today_game_minutes, today_completed_seconds = recorder.log_handler.get_today_stats()

            return MainWindowBootstrapResult(
                games=games,
                browsers=browsers,
                scanner=scanner,
                recorder=recorder,
                state_tracker=state_tracker,
                today_game_minutes=today_game_minutes,
                today_completed_seconds=today_completed_seconds,
            )
        except NoGamesConfiguredError as e:
            raise MainWindowBootstrapError(
                'ゲーム情報が取得できませんでした（config.ini を確認）'
            ) from e
        except FileNotFoundError as e:
            raise MainWindowBootstrapError(
                '認証情報ファイルが見つかりません（config.ini を確認）',
                f'ログ用認証情報ファイルが見つかりません: {e}',
            ) from e
        except Exception as e:
            raise MainWindowBootstrapError(
                'ログハンドラー初期化エラー',
                f'ログハンドラーの初期化に失敗しました: {e}',
            ) from e


# =============================================================================
# メインウィンドウ
# =============================================================================
class MainWindow(QWidget):
    """メインウィンドウ."""

    def __init__(self) -> None:
        super().__init__()
        self._initialize_window_state()
        self.w = build_main_layout(self)
        self._initialize_runtime_state()
        self._initialize_window_title_copy()
        self._warmup_dependencies()
        self._init_components()
        self._start_background_timers()
        self._run_initial_refresh()

    def _initialize_window_state(self) -> None:
        """タイトルと永続化されたウィンドウ状態を初期適用する."""
        self.setWindowTitle(BASE_TITLE)
        (
            x,
            y,
            self.display_mode,
            self.mode_sizes,
            self.overtime_alert_enabled,
        ) = self._get_state_controller().load_all()
        self.setGeometry(x, y, *self.mode_sizes[self.display_mode])

    def _initialize_runtime_state(self) -> None:
        """実行時状態の初期値を設定する."""
        self.games: List[GameEntry] = []
        self.browsers: Sequence[str] = DEFAULT_BROWSERS
        self.scanner: WindowScanner
        self.recorder: SessionRecorder
        self.daily_stats = DailyStatsTracker()
        self.active_games_cache: List[GameEntry] = []
        self.inactive_games_cache: List[GameEntry] = []
        self.latest_window_titles: List[str] = []
        self.overlay_window: Optional[TodayTimeOverlayWindow] = None
        self.overtime_alert_enabled = bool(
            getattr(self, "overtime_alert_enabled", DEFAULT_OVERTIME_ALERT_ENABLED)
        )
        self._overtime_alert_toggle_connected = False
        self._overtime_alert_tracker = OvertimeAlertTracker(
            thresholds_minutes=OVERTIME_ALERT_THRESHOLDS_MINUTES,
            alerted_threshold_minutes=set(),
        )
        self._window_title_copy_connected = False

    def _get_window_list_widget(self) -> Optional[QWidget]:
        """window_list ウィジェットを安全に取得する。"""
        return cast(Optional[QWidget], getattr(getattr(self, "w", None), "window_list", None))

    def _initialize_window_title_copy(self) -> None:
        """現在のウィンドウタイトル一覧のクリックコピーを初期化する。"""
        window_list = self._get_window_list_widget()
        if window_list is None or self._window_title_copy_connected:
            return

        item_clicked_signal = getattr(window_list, "itemClicked", None)
        if item_clicked_signal is None:
            return

        try:
            item_clicked_signal.connect(self._on_window_title_item_clicked)
        except Exception:
            return

        self._window_title_copy_connected = True

        set_tooltip = getattr(window_list, "setToolTip", None)
        if callable(set_tooltip):
            set_tooltip("クリックした行のタイトルをコピー")

    def _on_window_title_item_clicked(self, item: object) -> None:
        """現在のウィンドウタイトル一覧の行クリック時に文字列をコピーする。"""
        if item is None:
            return

        text_getter = getattr(item, "text", None)
        if not callable(text_getter):
            return

        try:
            text = str(text_getter())
        except Exception:
            return

        self._copy_text_to_clipboard(text)

    def _copy_text_to_clipboard(self, text: str) -> None:
        """指定テキストをクリップボードへコピーする。"""
        if not text or not text.strip():
            return

        clipboard_getter = getattr(QApplication, "clipboard", None)
        if not callable(clipboard_getter):
            return

        try:
            clipboard = clipboard_getter()
        except Exception:
            return
        if clipboard is None:
            return

        set_text = getattr(clipboard, "setText", None)
        if not callable(set_text):
            return

        try:
            set_text(text)
        except Exception:
            return
        self._set_status("ウィンドウタイトルをコピーしました")

    def _warmup_dependencies(self) -> None:
        """起動直後に使う依存を事前生成する."""
        self._get_ui_controller()
        self._get_display_controller()
        self._get_loop_controller()
        self._get_overlay_controller()
        self._get_bootstrapper()

    def _start_background_timers(self) -> None:
        """バックグラウンド更新タイマーを開始する."""
        # タイマーをインスタンス変数に保持（GCによる停止防止）
        self._scan_timer = self._start_timer(POLL_INTERVAL_SECONDS, self._scan_tick)
        self._ui_timer = self._start_timer(UI_REFRESH_INTERVAL_SECONDS, self._ui_tick)

    def _run_initial_refresh(self) -> None:
        """起動直後の初回描画を実行する."""
        self._scan_tick()
        self._ui_tick()

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィンドウ終了時にプレイ中のゲームを記録し、状態を保存."""
        self._record_playing_games_before_close()
        self._save_window_state()
        self._close_overlay()
        super().closeEvent(event)

    def _record_playing_games_before_close(self) -> None:
        """終了時に記録対象のプレイ中ゲームを記録する."""
        for game in self._iter_recordable_games():
            self.recorder.record(game)

    def _iter_recordable_games(self) -> Sequence[GameEntry]:
        """終了時に記録対象となるゲームを返す."""
        return [
            game
            for game in getattr(self, "games", [])
            if game.is_playing and game.start_time
        ]

    def _start_timer(self, interval_seconds: float, callback: Callable[[], None]) -> QTimer:
        """タイマーを作成して開始."""
        return self._get_loop_controller().start_timer(self, interval_seconds, callback)

    def _disable_with_status(self, message: str) -> None:
        """ステータスを表示してUIを無効化."""
        self._set_status(message)
        self.setDisabled(True)

    def _ensure_daily_stats(self) -> DailyStatsTracker:
        """daily_stats を必ず返す."""
        daily_stats = getattr(self, "daily_stats", None)
        if daily_stats is None:
            daily_stats = DailyStatsTracker()
            self.daily_stats = daily_stats
        return daily_stats

    def _resolve_dependency(
        self,
        attr_name: str,
        *,
        factory: Callable[[], TDependency],
        validator: Optional[Callable[[TDependency], bool]] = None,
    ) -> TDependency:
        """キャッシュ済み依存を再利用し、必要時のみ再生成する."""
        dependency = cast(Optional[TDependency], getattr(self, attr_name, None))
        if dependency is None or (validator is not None and not validator(dependency)):
            dependency = factory()
            setattr(self, attr_name, dependency)
        return dependency

    def _get_bootstrapper(self) -> MainWindowBootstrapper:
        """初期化ブートストラッパーを返す."""
        daily_stats = self._ensure_daily_stats()
        return self._resolve_dependency(
            "_bootstrapper",
            factory=lambda: MainWindowBootstrapper(
                base_title=BASE_TITLE,
                min_play_minutes=MIN_PLAY_MINUTES,
                inactive_timeout_minutes=INACTIVE_TIMEOUT_MINUTES,
                daily_stats=daily_stats,
            ),
            validator=lambda bootstrapper: bootstrapper.daily_stats is daily_stats,
        )

    def _apply_bootstrap_result(self, result: MainWindowBootstrapResult) -> None:
        """ブートストラップ結果を MainWindow の状態へ反映."""
        self.games = result.games
        self.browsers = result.browsers
        self.scanner = result.scanner
        self.recorder = result.recorder
        self.state_tracker = result.state_tracker
        self.daily_stats.today_game_minutes_cache = result.today_game_minutes
        self.daily_stats.today_completed_seconds = result.today_completed_seconds

    def _get_ui_controller(self) -> MainWindowUiController:
        """現在の widget / stats に同期した UI コントローラーを返す."""
        daily_stats = self._ensure_daily_stats()
        return self._resolve_dependency(
            "_ui_controller",
            factory=lambda: MainWindowUiController(self.w, daily_stats),
            validator=lambda controller: (
                controller.w is self.w
                and controller.daily_stats is daily_stats
            ),
        )

    def _get_display_controller(self) -> MainWindowDisplayController:
        """表示モード制御コントローラーを返す."""
        return self._resolve_dependency(
            "_display_controller",
            factory=lambda: MainWindowDisplayController(MAX_WIDGET_HEIGHT),
        )

    def _get_state_controller(self) -> MainWindowStateController:
        """状態保存コントローラーを返す."""
        return self._resolve_dependency(
            "_state_controller",
            factory=lambda: MainWindowStateController(STATE_FILE),
        )

    def _get_loop_controller(self) -> MainWindowLoopController:
        """tick/タイマー制御コントローラーを返す."""
        return self._resolve_dependency(
            "_loop_controller",
            factory=MainWindowLoopController,
        )

    def _get_overlay_controller(self) -> MainWindowOverlayController:
        """オーバーレイ表示制御コントローラーを返す."""
        return self._resolve_dependency(
            "_overlay_controller",
            factory=lambda: MainWindowOverlayController(self),
            validator=lambda controller: controller.owner is self,
        )

    def _init_components(self) -> None:
        """設定を読み込みコンポーネントを初期化."""
        try:
            result = self._get_bootstrapper().bootstrap(window_title=self.windowTitle())
        except MainWindowBootstrapError as e:
            if e.log_message:
                logger.error(e.log_message)
            self._disable_with_status(e.status_message)
            return

        self._apply_bootstrap_result(result)
        self._initialize_overtime_alert_toggle()
        self._apply_display_mode()
        self._apply_mode_geometry()
        self._set_status(Messages.NO_GAME_PLAYING)
        self._initialize_overlay()

    def _scan_tick(self) -> None:
        """監視サイクル（1秒間隔）."""
        self._get_loop_controller().run_scan_tick(self)

    def _scan_games(self, window_titles: List[str], foreground_title: Optional[str]) -> ScanResult:
        """GameStateTracker にゲーム状態スキャンを委譲."""
        return self.state_tracker.scan(
            games=self.games,
            window_titles=window_titles,
            foreground_title=foreground_title,
            load_today_game_minutes_callback=self._load_today_game_minutes,
        )

    def _apply_scan_result(self, window_titles: List[str], result: ScanResult) -> None:
        """スキャン結果をキャッシュと UI に反映."""
        self.latest_window_titles = window_titles
        self.active_games_cache = result.active_games
        self.inactive_games_cache = result.inactive_games
        self._update_active_list(result.active_games, result.inactive_games)
        self._update_window_list(window_titles)
        self._update_scan_status(result.active_games, result.inactive_games)

    def _update_scan_status(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> None:
        """スキャン結果に応じてステータスメッセージを更新."""
        if active_games or inactive_games:
            self._set_status('プレイ時間計測中')
        else:
            self._set_status(Messages.NO_GAME_PLAYING)

    def _update_active_list(self, active_games: List[GameEntry], inactive_games: List[GameEntry]) -> None:
        """プレイ中ゲームリストを更新."""
        self._get_ui_controller().update_active_list(active_games, inactive_games)

    def _all_playing_games(self, active_games: Optional[Sequence[GameEntry]] = None) -> List[GameEntry]:
        """アクティブ/非アクティブを統合した、現在プレイ中のゲーム一覧を返す."""
        active = active_games if active_games is not None else self.active_games_cache
        return self._get_ui_controller().all_playing_games(active, self.inactive_games_cache)


    def _update_session_times(self, active_games: List[GameEntry], now: datetime) -> None:
        """現在のセッション時間を更新（最長セッションを表示）.
        
        active_games と inactive_games_cache を合わせた全プレイ中ゲームから最長を表示。
        """
        self._get_ui_controller().update_session_times(
            active_games,
            self.inactive_games_cache,
            now,
        )

    def _update_today_totals(self, active_games: List[GameEntry], now: datetime) -> float:
        """今日のプレイ時間（完了+進行中）を更新.
        
        - 日跨ぎセッションは今日0:00以降のみカウント
        - 5分未満の進行中セッションは除外
        - 非アクティブ中のゲームも含む
        """
        return self._get_ui_controller().update_today_totals(
            active_games,
            self.inactive_games_cache,
            now,
        )

    def _update_window_list(self, window_titles: List[str]) -> None:
        """現在のウィンドウタイトルリストを更新."""
        self._get_ui_controller().update_window_list(window_titles)

    def _load_today_game_minutes(self) -> Dict[str, float]:
        """キャッシュから今日プレイしたゲームごとの分数を集計."""
        try:
            game_minutes, _ = self.recorder.log_handler.get_today_stats()
            return game_minutes
        except Exception as e:
            logger.error(f'今日のゲーム時間の集計中にエラーが発生しました: {e}')
            return {}

    def _update_today_games_list(self, now: datetime) -> None:
        """今日プレイしたゲームの一覧と時間を更新."""
        self._get_ui_controller().update_today_games_list(
            self.active_games_cache,
            self.inactive_games_cache,
            now,
        )

    def _load_today_completed_seconds(self) -> float:
        """起動時に今日分の完了プレイ時間をロード（キャッシュ使用）."""
        try:
            _, completed_seconds = self.recorder.log_handler.get_today_stats()
            return completed_seconds
        except Exception as e:
            logger.error(f'今日の完了プレイ時間のロード中にエラーが発生しました: {e}')
            return 0.0

    def _save_window_state(self) -> None:
        """ウィンドウ位置・サイズ・表示モードを保存."""
        self._get_state_controller().save(
            self.geometry(),
            self.display_mode,
            self.mode_sizes,
            self._is_overtime_alert_enabled(),
        )

    def _set_status(self, message: str) -> None:
        """ステータスメッセージをタイトルバーに反映。"""
        title = f"{BASE_TITLE} - {message}" if message else BASE_TITLE
        self.setWindowTitle(title)
        if hasattr(self, "scanner"):
            self.scanner.excluded_titles.add(title)

    def _initialize_overlay(self) -> None:
        """今日のプレイ時間オーバーレイを初期化する."""
        self._get_overlay_controller().initialize_overlay()

    def _is_overtime_alert_enabled(self) -> bool:
        """時間超過防止アラートの有効/無効を返す。"""
        return bool(getattr(self, "overtime_alert_enabled", DEFAULT_OVERTIME_ALERT_ENABLED))

    def _set_overtime_alert_enabled(self, enabled: bool) -> None:
        """時間超過防止アラートの有効/無効を設定する。"""
        self.overtime_alert_enabled = bool(enabled)

    def _get_overtime_alert_tracker(self) -> OvertimeAlertTracker:
        """時間超過防止アラート進捗トラッカーを返す。"""
        tracker = getattr(self, "_overtime_alert_tracker", None)
        if tracker is None:
            tracker = OvertimeAlertTracker(
                thresholds_minutes=OVERTIME_ALERT_THRESHOLDS_MINUTES,
                alerted_threshold_minutes=set(),
            )
            self._overtime_alert_tracker = tracker
        return cast(OvertimeAlertTracker, tracker)

    def _get_overtime_alert_toggle(self) -> Optional[QPushButton]:
        """時間超過防止アラートのトグルを取得する。"""
        return cast(Optional[QPushButton], getattr(getattr(self, "w", None), "overtime_alert_toggle", None))

    def _initialize_overtime_alert_toggle(self) -> None:
        """時間超過防止アラートトグルを初期化する。"""
        toggle = self._get_overtime_alert_toggle()
        if toggle is None:
            return

        toggle.blockSignals(True)
        toggle.setChecked(self._is_overtime_alert_enabled())
        toggle.blockSignals(False)

        if getattr(self, "_overtime_alert_toggle_connected", False):
            try:
                toggle.toggled.disconnect(self._on_overtime_alert_toggled)
            except (TypeError, RuntimeError):
                pass
        toggle.toggled.connect(self._on_overtime_alert_toggled)
        self._overtime_alert_toggle_connected = True

    def _on_overtime_alert_toggled(self, checked: bool) -> None:
        """時間超過防止アラートトグル変更時の処理。"""
        self._set_overtime_alert_enabled(checked)

        now = datetime.now()
        total_seconds = self._get_ui_controller().calculate_today_total_seconds(
            self.active_games_cache,
            self.inactive_games_cache,
            now,
        )
        self._prime_overtime_alert_progress(total_seconds)
        self._sync_overlay()

    def _prime_overtime_alert_progress(self, total_seconds: float) -> None:
        """現在値を基準にアラート進捗を初期化し、遡及通知を抑止する。"""
        self._get_overtime_alert_tracker().prime(total_seconds)

    def _emit_overtime_alert(self, threshold_minutes: int) -> None:
        """閾値到達アラートを通知する。"""
        try:
            QApplication.beep()
        except Exception:
            pass
        logger.info("プレイ時間アラート: %s分に到達しました", threshold_minutes)

    def _update_overtime_alert(self, total_seconds: float) -> None:
        """閾値跨ぎを検知して時間超過防止アラートを鳴らす。"""
        tracker = self._get_overtime_alert_tracker()
        triggered_minutes = tracker.update(
            total_seconds,
            alerts_enabled=self._is_overtime_alert_enabled(),
        )
        for minute in triggered_minutes:
            self._emit_overtime_alert(minute)

    def _get_overlay_window(self) -> Optional[TodayTimeOverlayWindow]:
        """現在のオーバーレイウィンドウを返す。"""
        return cast(Optional[TodayTimeOverlayWindow], getattr(self, "overlay_window", None))

    def _get_today_time_display(self) -> Optional[QWidget]:
        """today_time_display ウィジェットを安全に取得する。"""
        return cast(Optional[QWidget], getattr(getattr(self, "w", None), "today_time_display", None))

    def _refresh_overlay_time(self) -> None:
        """オーバーレイの時刻表示を更新する."""
        self._get_overlay_controller().refresh_overlay_time()

    def _sync_overlay_geometry(self) -> None:
        """オーバーレイを today_time_display の位置とサイズに追従させる."""
        self._get_overlay_controller().sync_overlay_geometry()

    @staticmethod
    def _global_rect_of_widget(widget: QWidget) -> Optional[Rect]:
        """ウィジェットのグローバル矩形を返す."""
        try:
            top_left = widget.mapToGlobal(widget.rect().topLeft())
            return (
                int(top_left.x()),
                int(top_left.y()),
                int(top_left.x() + widget.width()),
                int(top_left.y() + widget.height()),
            )
        except Exception:
            return None

    @staticmethod
    def _window_rect(hwnd: int) -> Optional[Rect]:
        """指定HWNDのスクリーン矩形を返す."""
        if _USER32 is None or hwnd == 0:
            return None

        rect = _WinRect()
        if _USER32.GetWindowRect(int(hwnd), ctypes.byref(rect)) == 0:
            return None
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))

    @staticmethod
    def _rect_contains_point(rect: Rect, x: int, y: int) -> bool:
        """矩形が点を含むか判定する."""
        return rect[0] <= x < rect[2] and rect[1] <= y < rect[3]

    @staticmethod
    def _rects_intersect(
        first_rect: Rect,
        second_rect: Rect,
    ) -> bool:
        """2つの矩形が交差しているか判定する."""
        left = max(first_rect[0], second_rect[0])
        top = max(first_rect[1], second_rect[1])
        right = min(first_rect[2], second_rect[2])
        bottom = min(first_rect[3], second_rect[3])
        return right > left and bottom > top

    @staticmethod
    def _sample_points_from_rect(rect: Rect) -> List[Point]:
        """矩形内の5サンプル点（中心 + 四隅寄り）を返す."""
        left, top, right, bottom = rect
        width = max(1, right - left)
        height = max(1, bottom - top)
        points: List[Point] = []

        for x_ratio, y_ratio in OVERLAY_SAMPLE_RATIOS:
            x = left + int(width * x_ratio)
            y = top + int(height * y_ratio)
            x = min(max(x, left), right - 1)
            y = min(max(y, top), bottom - 1)
            points.append((x, y))
        return points

    @staticmethod
    def _window_at_point(x: int, y: int) -> int:
        """スクリーン座標の最前面ウィンドウHWNDを返す."""
        if _USER32 is None:
            return 0
        try:
            return int(_USER32.WindowFromPoint(_WinPoint(int(x), int(y))) or 0)
        except Exception:
            return 0

    @staticmethod
    def _window_below(hwnd: int) -> int:
        """指定HWNDの背面にある次ウィンドウHWNDを返す."""
        if _USER32 is None or hwnd == 0:
            return 0
        # GW_HWNDNEXT = 2
        try:
            return int(_USER32.GetWindow(int(hwnd), 2) or 0)
        except Exception:
            return 0

    @staticmethod
    def _root_window(hwnd: int) -> int:
        """指定HWNDのルートウィンドウHWNDを返す."""
        if _USER32 is None or hwnd == 0:
            return 0
        # GA_ROOT = 2
        try:
            return int(_USER32.GetAncestor(int(hwnd), 2) or 0)
        except Exception:
            return 0

    @staticmethod
    def _window_handle_of(widget: Optional[QWidget]) -> int:
        """QWidgetからHWNDを安全に取得する."""
        if widget is None:
            return 0
        win_id_callable = getattr(widget, "winId", None)
        if not callable(win_id_callable):
            return 0
        try:
            return int(win_id_callable())
        except Exception:
            return 0

    def _is_own_window(self, hwnd: int) -> bool:
        """指定HWNDがMainWindowまたはオーバーレイ自身か判定する."""
        if hwnd == 0:
            return False
        if _USER32 is None:
            return False

        # 同一プロセスのウィンドウはすべて「自ウィンドウ」とみなす。
        # (Qtの子HWND/ネイティブハンドル差異での誤判定を避けるため)
        process_id = ctypes.c_uint(0)
        _USER32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(process_id))
        if int(process_id.value) == os.getpid():
            return True

        root_hwnd = self._root_window(hwnd)
        main_hwnd = self._root_window(self._window_handle_of(self))
        overlay_hwnd = self._root_window(self._window_handle_of(getattr(self, "overlay_window", None)))
        return root_hwnd in {main_hwnd, overlay_hwnd}

    def _native_scale_factor(self) -> float:
        """Qt論理座標 -> Win32物理解像度座標へのスケールを推定する."""
        if _USER32 is None:
            return 1.0

        hwnd = self._window_handle_of(self)
        rect = self._window_rect(hwnd)
        logical_w = int(getattr(self, "width", lambda: 0)())
        logical_h = int(getattr(self, "height", lambda: 0)())
        if rect is None or logical_w <= 0 or logical_h <= 0:
            return 1.0

        native_w = max(1, rect[2] - rect[0])
        native_h = max(1, rect[3] - rect[1])
        scale_x = native_w / logical_w
        scale_y = native_h / logical_h
        scale = (scale_x + scale_y) / 2.0
        if 0.75 <= scale <= 3.0:
            return scale
        return 1.0

    def _to_native_point(self, x: int, y: int) -> Point:
        """Qt論理座標の点をWin32 API用の物理解像度座標へ変換する."""
        scale = self._native_scale_factor()
        return int(round(x * scale)), int(round(y * scale))

    def _to_native_rect(self, rect: Rect) -> Rect:
        """Qt論理座標の矩形をWin32 API用の物理解像度座標へ変換する."""
        left_top = self._to_native_point(rect[0], rect[1])
        right_bottom = self._to_native_point(rect[2], rect[3])
        return (
            min(left_top[0], right_bottom[0]),
            min(left_top[1], right_bottom[1]),
            max(left_top[0], right_bottom[0]),
            max(left_top[1], right_bottom[1]),
        )

    def _foreground_rect_if_foreign(self) -> Optional[Rect]:
        """前面ウィンドウが他ウィンドウの場合のみ、その矩形を返す."""
        if _USER32 is None:
            return None

        foreground_hwnd = int(_USER32.GetForegroundWindow() or 0)
        if foreground_hwnd == 0 or self._is_own_window(foreground_hwnd):
            return None
        return self._window_rect(foreground_hwnd)

    def _find_covering_foreign_window_at_point(self, x: int, y: int) -> int:
        """点を覆う「自ウィンドウ以外」のHWNDを探索して返す。"""
        hwnd = self._window_at_point(x, y)
        if hwnd == 0:
            return 0

        # 判定時点で自ウィンドウが最前面なら、その点は露出しているとみなす。
        if self._is_own_window(hwnd):
            return 0

        walk_count = 0

        while hwnd and walk_count < MAX_Z_WALK:
            if not self._is_own_window(hwnd):
                hwnd_rect = self._window_rect(hwnd)
                if hwnd_rect is not None and self._rect_contains_point(hwnd_rect, x, y):
                    return hwnd
            hwnd = self._window_below(hwnd)
            walk_count += 1

        if walk_count >= MAX_Z_WALK:
            logger.debug("overlay z-order walk reached MAX_Z_WALK=%s", MAX_Z_WALK)
        return 0

    def _is_today_display_covered_by_foreground_window(self) -> bool:
        """today_time_displayのサンプル点が他ウィンドウに覆われているか判定する."""
        target = self._get_today_time_display()
        if target is None:
            return False

        target_rect = self._global_rect_of_widget(target)
        if target_rect is None:
            return False

        # 前面ウィンドウの外接矩形が対象領域と交差しない場合は未被覆扱いにする。
        foreground_rect = self._foreground_rect_if_foreign()
        if foreground_rect is None:
            return False

        target_rect_native = self._to_native_rect(target_rect)
        if not self._rects_intersect(target_rect_native, foreground_rect):
            return False

        sample_points = self._sample_points_from_rect(target_rect)
        return any(
            self._find_covering_foreign_window_at_point(*self._to_native_point(x, y)) != 0
            for x, y in sample_points
        )

    def _should_show_overlay(self) -> bool:
        """メインウィンドウ背面かつtoday表示部が重なっている時のみオーバーレイ表示."""
        return self._get_overlay_controller().should_show_overlay()

    def _sync_overlay_visibility(self) -> None:
        """表示条件に応じてオーバーレイを表示/非表示する."""
        self._get_overlay_controller().sync_overlay_visibility()

    def _sync_overlay(self) -> None:
        """オーバーレイの表示内容・位置・可視状態を同期する."""
        self._get_overlay_controller().sync_overlay()

    def _close_overlay(self) -> None:
        """オーバーレイを閉じて参照を解放する."""
        self._get_overlay_controller().close_overlay()

    def _apply_mode_geometry(self) -> None:
        """表示モードに応じたサイズを適用."""
        self._get_display_controller().apply_mode_geometry(
            self,
            self.display_mode,
            self.mode_sizes,
        )

    def _apply_display_mode(self) -> None:
        """表示モードに応じてウィジェット表示を切り替え。"""
        self._get_display_controller().apply_display_mode(
            display_mode=self.display_mode,
            widgets=self.w,
            set_widget_visibility=self._set_widget_visibility,
            set_widget_with_height=self._set_widget_with_height,
            apply_mode_geometry=self._apply_mode_geometry,
        )

    def _set_widget_visibility(self, widget: QWidget, visible: bool) -> None:
        """ウィジェットの表示/非表示を設定."""
        self._get_display_controller().set_widget_visibility(widget, visible)

    def _set_widget_with_height(self, widget: QWidget, visible: bool, *, min_height: int, max_height: int) -> None:
        """ウィジェットの表示/非表示と高さ制約を設定."""
        self._get_display_controller().set_widget_with_height(
            widget,
            visible,
            min_height=min_height,
            max_height=max_height,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """クリックで表示モードをトグル。"""
        if self._should_cycle_display_mode(event):
            self._cycle_display_mode()
        super().mousePressEvent(event)

    @staticmethod
    def _should_cycle_display_mode(event: QMouseEvent) -> bool:
        """表示モード切り替え対象のクリックかを判定."""
        return event.button() == Qt.MouseButton.LeftButton

    def _cycle_display_mode(self) -> None:
        """表示モードを循環。"""
        self.display_mode = self._get_display_controller().next_display_mode(self.display_mode)
        self._apply_display_mode()
        self._save_window_state()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """リサイズ時に現在モードのサイズを記録."""
        self._record_current_mode_size()
        super().resizeEvent(event)

    def _record_current_mode_size(self) -> None:
        """現在の表示モードに対応するサイズを保存する."""
        self._get_state_controller().record_resize(
            self.mode_sizes,
            self.display_mode,
            self.width(),
            self.height(),
        )

    def _ui_tick(self) -> None:
        """UIだけを高速更新（0.1秒間隔）."""
        self._get_loop_controller().run_ui_tick(self)
        self._sync_overlay()


# =============================================================================
# エントリーポイント
# =============================================================================
def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
