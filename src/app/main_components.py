"""MainWindow の補助コンポーネント群。"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypeVar,
    cast,
)

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.models import GameEntry
from src.core.services import (
    DailyStatsTracker,
    GameInfoLoader,
    GameStateTracker,
    Messages,
    MIN_PLAY_MINUTES,
    ScanResult,
    SessionRecorder,
    WindowScanner,
)
from src.core.time_utils import (
    SECONDS_PER_MINUTE,
    calc_today_elapsed_seconds,
    format_hms,
)
from src.core.window_state import DISPLAY_MODES, MODE_DEFAULT_SIZES, WindowState
from src.infra.config_loader import ConfigLoader, ConfigNotConfiguredError
from src.infra.log_handler import LogHandler
from src.infra.settings_store import SettingsStore
from src.ui.gui_layout import LayoutWidgets

logger = logging.getLogger(__name__)

OVERLAY_FALLBACK_WIDTH = 240
OVERLAY_FALLBACK_HEIGHT = 40
MIN_MODE_SAFE_WIDTH = 320
MIN_MODE_SAFE_HEIGHT = 110


class _GeometryLike(Protocol):
    """QRect 互換の最小インターフェース."""

    def width(self) -> int: ...
    def height(self) -> int: ...
    def x(self) -> int: ...
    def y(self) -> int: ...


def clamp_mode_size(display_mode: str, width: int, height: int) -> Tuple[int, int]:
    """表示モードごとの最低サイズを保証する。"""
    if display_mode == "min":
        return max(width, MIN_MODE_SAFE_WIDTH), max(height, MIN_MODE_SAFE_HEIGHT)
    return width, height


class TodayTimeOverlayWindow(QWidget):
    """フルスクリーンゲーム中に表示する、今日の時間専用オーバーレイ."""

    def __init__(self) -> None:
        super().__init__()
        self._time_display = QLabel("00:00:00.0", self)
        self._configure_window()
        self._build_layout()
        self.resize(OVERLAY_FALLBACK_WIDTH, OVERLAY_FALLBACK_HEIGHT)

    @staticmethod
    def _window_flag(flag_name: str) -> Any:
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
            self.setAttribute(cast(Any, attribute), enabled)

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
        total_seconds = self.calculate_today_total_seconds(
            active_games, inactive_games, now)
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
                game_minutes[game.game_title] = game_minutes.get(
                    game.game_title, 0) + current_minutes

        sorted_games = sorted(game_minutes.items(), key=lambda x: x[1], reverse=True)
        content = '\n'.join(
            f'{game_title}: {int(minutes)}分' for game_title, minutes in sorted_games)

        if content != self.daily_stats.last_today_games_content:
            self.daily_stats.last_today_games_content = content
            self.w.today_games_table.setRowCount(len(sorted_games))
            for row, (game_title, minutes) in enumerate(sorted_games):
                self.w.today_games_table.setItem(row, 0, QTableWidgetItem(game_title))
                self.w.today_games_table.setItem(
                    row, 1, QTableWidgetItem(f'{int(minutes)}分'))


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
        if widgets.report_button is not None:
            set_widget_visibility(widgets.report_button, True)

        apply_mode_geometry()

    def next_display_mode(self, current_display_mode: str) -> str:
        """現在の表示モードから次のモードを返す."""
        idx = DISPLAY_MODES.index(current_display_mode)
        return DISPLAY_MODES[(idx + 1) % len(DISPLAY_MODES)]


class MainWindowStateController:
    """MainWindow の状態読み書きロジック."""

    def __init__(
        self,
        state_file: Path,
        settings_store: Optional[SettingsStore] = None,
    ) -> None:
        self.state_file = state_file
        self.settings_store = settings_store or SettingsStore()
        self.settings_store.migrate_window_state_file(self.state_file)

    def load_all(self) -> Tuple[int, int, str, Dict[str, Tuple[int, int]], bool]:
        """永続化されたウィンドウ状態と設定を読み込む."""
        data = self.settings_store.load_window_state()
        if data is None:
            return WindowState.load_all(self.state_file)
        return WindowState.load_all_from_data(data)

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
        geom: _GeometryLike,
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
        data = WindowState.to_data(
            geom.x(),
            geom.y(),
            display_mode,
            mode_sizes,
            overtime_alert_enabled=bool(overtime_alert_enabled),
        )
        self.settings_store.save_window_state(data)

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

    def __init__(self, timer_factory: Callable[[QWidget], QTimer] = QTimer) -> None:
        self._timer_factory = timer_factory

    def start_timer(
        self,
        owner: QWidget,
        interval_seconds: float,
        callback: Callable[[], None],
    ) -> QTimer:
        """タイマーを作成して開始."""
        timer = self._timer_factory(owner)
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
        self._last_overlay_should_show: Optional[bool] = None
        self._last_overlay_reason: Optional[str] = None
        self._last_overlay_log_monotonic: float = 0.0

    def initialize_overlay(self) -> None:
        """今日のプレイ時間オーバーレイを初期化する."""
        if self.owner._get_overlay_window() is not None:
            return

        try:
            self.owner.overlay_window = TodayTimeOverlayWindow()
            self.owner.overlay_window.hide()
            self.sync_overlay()
        except Exception as e:
            logger.warning("オーバーレイ初期化に失敗したため無効化します: %s", e)
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
            logger.debug("オーバーレイジオメトリの同期に失敗", exc_info=True)
            return

    def _evaluate_overlay_visibility(self) -> Tuple[bool, str]:
        """オーバーレイ表示可否と理由を返す."""
        if not self.owner._is_overtime_alert_enabled():
            return False, "overtime_alert_disabled"

        is_minimized = getattr(self.owner, "isMinimized", lambda: False)()
        is_visible = getattr(self.owner, "isVisible", lambda: True)()
        if is_minimized or not is_visible:
            return False, "window_hidden_or_minimized"

        # QtのisActiveWindowは環境差で不安定なケースがあるため、
        # Win32の前面ウィンドウ判定を優先する。
        if self.owner._foreground_rect_if_foreign() is None:
            return False, "window_foreground_or_no_foreign"

        cover_state_getter = getattr(self.owner, "_get_today_display_cover_state", None)
        if callable(cover_state_getter):
            covered, cover_reason = cast(Tuple[bool, str], cover_state_getter())
        else:
            covered = bool(self.owner._is_today_display_covered_by_foreground_window())
            cover_reason = "covered_legacy" if covered else "not_covered_legacy"

        if covered:
            return True, cover_reason
        return False, cover_reason

    def should_show_overlay(self) -> bool:
        """メインウィンドウ背面かつtoday表示部が重なっている時のみ表示."""
        should_show, _ = self._evaluate_overlay_visibility()
        return should_show

    def _log_overlay_visibility(self, should_show: bool, reason: str) -> None:
        """判定理由を状態変化時または定期的にINFO出力する。"""
        now = time.monotonic()
        state_changed = (
            self._last_overlay_should_show != should_show
            or self._last_overlay_reason != reason
        )
        should_log = state_changed or (now - self._last_overlay_log_monotonic >= 5.0)
        if not should_log:
            return

        logger.info(
            "overlay visibility: %s (%s)",
            "show" if should_show else "hide",
            reason,
        )
        self._last_overlay_should_show = should_show
        self._last_overlay_reason = reason
        self._last_overlay_log_monotonic = now

    def sync_overlay_visibility(self) -> None:
        """表示条件に応じてオーバーレイを表示/非表示する."""
        overlay_window = self.owner._get_overlay_window()
        if overlay_window is None:
            return

        # オーバーレイ自身をヒットテスト対象から外して被覆判定する。
        was_visible = bool(getattr(overlay_window, "isVisible", lambda: False)())
        if was_visible:
            overlay_window.hide()

        should_show, reason = self._evaluate_overlay_visibility()
        self._log_overlay_visibility(should_show, reason)

        if should_show:
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

    def __init__(
        self,
        status_message: str,
        log_message: Optional[str] = None,
        *,
        open_settings: bool = False,
        alert_title: Optional[str] = None,
        alert_message: Optional[str] = None,
    ) -> None:
        super().__init__(status_message)
        self.status_message = status_message
        self.log_message = log_message
        self.open_settings = open_settings
        self.alert_title = alert_title
        self.alert_message = alert_message


class MainWindowBootstrapper:
    """MainWindow の依存構築・初期データ読み込みを担当."""

    def __init__(
        self,
        *,
        base_title: str,
        min_play_minutes: int,
        inactive_timeout_minutes: int,
        daily_stats: DailyStatsTracker,
        config_loader_cls: type = ConfigLoader,
        game_info_loader_cls: type = GameInfoLoader,
        window_scanner_cls: type = WindowScanner,
        log_handler_cls: type = LogHandler,
        session_recorder_cls: type = SessionRecorder,
        game_state_tracker_cls: type = GameStateTracker,
    ) -> None:
        self.base_title = base_title
        self.min_play_minutes = min_play_minutes
        self.inactive_timeout_minutes = inactive_timeout_minutes
        self.daily_stats = daily_stats
        self._config_loader_cls = config_loader_cls
        self._game_info_loader_cls = game_info_loader_cls
        self._window_scanner_cls = window_scanner_cls
        self._log_handler_cls = log_handler_cls
        self._session_recorder_cls = session_recorder_cls
        self._game_state_tracker_cls = game_state_tracker_cls

    def bootstrap(self, *, window_title: str) -> MainWindowBootstrapResult:
        """設定・サービス・初期統計をまとめて構築する."""
        try:
            config = self._config_loader_cls().load()
            games = self._game_info_loader_cls(config).load()
            if not games:
                raise NoGamesConfiguredError

            browsers = config.window_scan.browsers
            scanner = self._window_scanner_cls(
                excluded_titles=(
                    list(config.window_scan.excluded_titles)
                    + [self.base_title, window_title]
                )
            )

            log_handler = self._log_handler_cls(config.log_handler)
            recorder = self._session_recorder_cls(
                log_handler=log_handler,
                min_play_minutes=self.min_play_minutes,
            )
            state_tracker = self._game_state_tracker_cls(
                recorder=recorder,
                daily_stats=self.daily_stats,
                browsers=list(browsers),
                inactive_timeout_minutes=self.inactive_timeout_minutes,
            )
            today_game_minutes, today_completed_seconds = (
                recorder.log_handler.get_today_stats()
            )

            return MainWindowBootstrapResult(
                games=games,
                browsers=browsers,
                scanner=scanner,
                recorder=recorder,
                state_tracker=state_tracker,
                today_game_minutes=today_game_minutes,
                today_completed_seconds=today_completed_seconds,
            )
        except ConfigNotConfiguredError as e:
            raise MainWindowBootstrapError(
                "設定が未作成です。設定画面で入力して保存してください。",
                str(e),
                open_settings=True,
            ) from e
        except NoGamesConfiguredError as e:
            raise MainWindowBootstrapError(
                'ゲーム情報が取得できませんでした（config.ini を確認）'
            ) from e
        except FileNotFoundError as e:
            raise MainWindowBootstrapError(
                "認証情報ファイルが見つかりません。設定画面で認証JSONを確認してください。",
                f"認証情報ファイルが見つかりません: {e}",
                open_settings=True,
                alert_title="認証情報ファイルが見つかりません",
                alert_message=(
                    "設定されている認証JSONファイルを開けませんでした。\n"
                    "設定画面で認証JSONのパスを選び直してください。"
                ),
            ) from e
        except Exception as e:
            raise MainWindowBootstrapError(
                'ログハンドラー初期化エラー',
                f'ログハンドラーの初期化に失敗しました: {e}',
            ) from e
