"""Game Time Tracker - PySide6 GUI."""

import atexit
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, TypeVar, cast

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from src.app import main_components as components
from src.app.main_components import (
    MainWindowBootstrapError,
    MainWindowBootstrapResult,
    MainWindowBootstrapper,
    MainWindowDisplayController,
    MainWindowLoopController,
    MainWindowOverlayController,
    MainWindowStateController,
    MainWindowUiController,
    TodayTimeOverlayWindow,
)
from src.app.win32_helpers import (
    get_foreground_hwnd,
    global_rect_of_widget,
    is_own_process_window,
    Point,
    Rect,
    rect_contains_point,
    rects_intersect,
    root_window,
    sample_points_from_rect,
    window_at_point,
    window_below,
    window_handle_of,
    window_rect,
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
    calc_today_elapsed_seconds,
    format_hms,
    SECONDS_PER_MINUTE,
)
from src.core.window_state import (
    DEFAULT_OVERTIME_ALERT_ENABLED,
    DISPLAY_MODES,
    MODE_DEFAULT_SIZES,
    WindowState,
)
from src.infra.config_loader import (
    ConfigLoader,
    DEFAULT_BROWSERS,
    DEFAULT_EXCLUDED_TITLES,
)
from src.infra.log_handler import LogHandler
from src.infra.runtime_paths import (
    default_log_file,
    default_window_state_file,
    resolve_log_file,
    resolve_window_state_file,
)
from src.ui.gui_layout import build_main_layout
from src.ui.report_dialog import ReportDialog

logger = logging.getLogger(__name__)

_LOGGING_CONFIGURED = False
LOG_FILE_PATH = default_log_file()
LOG_DIR = LOG_FILE_PATH.parent
LOG_MAX_BYTES = 1 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def configure_logging() -> None:
    """アプリ起動時にロギングを初期化する（import時は実行しない）。"""
    global _LOGGING_CONFIGURED, LOG_DIR, LOG_FILE_PATH
    if _LOGGING_CONFIGURED:
        return

    root_logger = logging.getLogger()
    if root_logger.handlers:
        _LOGGING_CONFIGURED = True
        return

    LOG_FILE_PATH = resolve_log_file()
    LOG_DIR = LOG_FILE_PATH.parent
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE_PATH,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding='utf-8',
    )
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            file_handler,
        ],
    )
    atexit.register(logging.shutdown)
    _LOGGING_CONFIGURED = True


# =============================================================================
# 定数
# =============================================================================
POLL_INTERVAL_SECONDS = 1
INACTIVE_TIMEOUT_MINUTES = 5  # 非アクティブ状態でこの時間経過でセッション分割
STATE_FILE = default_window_state_file()
BASE_TITLE = "Game Time Tracker"
UI_REFRESH_INTERVAL_SECONDS = 0.1
MAX_WIDGET_HEIGHT = 16777215  # Qt default max height
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
OVERLAY_COVERED_POINTS_THRESHOLD = 2
OVERTIME_ALERT_THRESHOLDS_MINUTES: Tuple[int, ...] = (45, 50, 55, 58, 60)
TDependency = TypeVar("TDependency")


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
        self._report_button_connected = False
        self._report_dialog: Optional[ReportDialog] = None
        self._overtime_alert_tracker = OvertimeAlertTracker(
            thresholds_minutes=OVERTIME_ALERT_THRESHOLDS_MINUTES,
            alerted_threshold_minutes=set(),
        )
        self._window_title_copy_connected = False

    def _get_window_list_widget(self) -> Optional[QWidget]:
        """ウィンドウタイトル一覧ウィジェットを取得する。"""
        return getattr(self.w, "window_list", None)

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
            logger.debug("ウィンドウタイトルクリックシグナルの接続に失敗", exc_info=True)
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
            logger.debug("ウィンドウタイトルテキストの取得に失敗", exc_info=True)
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
            logger.debug("クリップボードの取得に失敗", exc_info=True)
            return
        if clipboard is None:
            return

        set_text = getattr(clipboard, "setText", None)
        if not callable(set_text):
            return

        try:
            set_text(text)
        except Exception:
            logger.debug("クリップボードへのコピーに失敗", exc_info=True)
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

    def _start_timer(
        self,
        interval_seconds: float,
        callback: Callable[[],
                           None]) -> QTimer:
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
                config_loader_cls=ConfigLoader,
                game_info_loader_cls=GameInfoLoader,
                window_scanner_cls=WindowScanner,
                log_handler_cls=LogHandler,
                session_recorder_cls=SessionRecorder,
                game_state_tracker_cls=GameStateTracker,
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
            factory=lambda: MainWindowStateController(resolve_window_state_file()),
        )

    def _get_loop_controller(self) -> MainWindowLoopController:
        """tick/タイマー制御コントローラーを返す."""
        return self._resolve_dependency(
            "_loop_controller",
            factory=lambda: MainWindowLoopController(timer_factory=QTimer),
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
        self._initialize_report_button()
        self._apply_display_mode()
        self._apply_mode_geometry()
        self._set_status(Messages.NO_GAME_PLAYING)
        self._initialize_overlay()

    def _scan_tick(self) -> None:
        """監視サイクル（1秒間隔）."""
        self._get_loop_controller().run_scan_tick(self)

    def _scan_games(
            self,
            window_titles: List[str],
            foreground_title: Optional[str]) -> ScanResult:
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

    def _update_active_list(
            self,
            active_games: List[GameEntry],
            inactive_games: List[GameEntry]) -> None:
        """プレイ中ゲームリストを更新."""
        self._get_ui_controller().update_active_list(active_games, inactive_games)

    def _all_playing_games(
            self,
            active_games: Optional[Sequence[GameEntry]] = None) -> List[GameEntry]:
        """アクティブ/非アクティブを統合した、現在プレイ中のゲーム一覧を返す."""
        active = active_games if active_games is not None else self.active_games_cache
        return self._get_ui_controller().all_playing_games(
            active,
            self.inactive_games_cache,
        )

    def _update_session_times(
            self,
            active_games: List[GameEntry],
            now: datetime) -> None:
        """現在のセッション時間を更新（最長セッションを表示）.

        active_games と inactive_games_cache を合わせた全プレイ中ゲームから最長を表示。
        """
        self._get_ui_controller().update_session_times(
            active_games,
            self.inactive_games_cache,
            now,
        )

    def _update_today_totals(
            self,
            active_games: List[GameEntry],
            now: datetime) -> float:
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
            logger.error('今日のゲーム時間の集計中にエラーが発生しました: %s', e)
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
            logger.error('今日の完了プレイ時間のロード中にエラーが発生しました: %s', e)
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
        return bool(
            getattr(
                self,
                "overtime_alert_enabled",
                DEFAULT_OVERTIME_ALERT_ENABLED))

    def _set_overtime_alert_enabled(self, enabled: bool) -> None:
        """時間超過防止アラートの有効/無効を設定する。"""
        self.overtime_alert_enabled = bool(enabled)

    def _get_overtime_alert_tracker(self) -> OvertimeAlertTracker:
        """時間超過防止アラート進捗トラッカーを返す。"""
        return self._overtime_alert_tracker

    def _get_overtime_alert_toggle(self) -> Optional[QPushButton]:
        """時間超過防止アラートのトグルを取得する。"""
        return self.w.overtime_alert_toggle

    def _get_report_button(self) -> Optional[QPushButton]:
        """Return the report button when the layout provides one."""
        return getattr(self.w, "report_button", None)

    def _initialize_overtime_alert_toggle(self) -> None:
        """時間超過防止アラートトグルを初期化する。"""
        toggle = self._get_overtime_alert_toggle()
        if toggle is None:
            return

        toggle.blockSignals(True)
        toggle.setChecked(self._is_overtime_alert_enabled())
        toggle.blockSignals(False)

        if self._overtime_alert_toggle_connected:
            try:
                toggle.toggled.disconnect(self._on_overtime_alert_toggled)
            except (TypeError, RuntimeError):
                pass
        toggle.toggled.connect(self._on_overtime_alert_toggled)
        self._overtime_alert_toggle_connected = True

    def _initialize_report_button(self) -> None:
        """Connect the report button to the report dialog."""
        button = self._get_report_button()
        if button is None:
            return

        if getattr(self, "_report_button_connected", False):
            try:
                button.clicked.disconnect(self._open_report_dialog)
            except (TypeError, RuntimeError):
                pass
        button.clicked.connect(self._open_report_dialog)
        self._report_button_connected = True

    def _open_report_dialog(self) -> None:
        """Open a non-modal report dialog backed by the cached log handler."""
        if not hasattr(self, "recorder"):
            return

        dialog = getattr(self, "_report_dialog", None)
        if dialog is None or not bool(getattr(dialog, "isVisible", lambda: False)()):
            dialog = ReportDialog(self.recorder.log_handler, self)
            self._report_dialog = dialog

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

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
            logger.debug("ビープ音の再生に失敗", exc_info=True)
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
        return self.overlay_window

    def _get_today_time_display(self) -> Optional[QLabel]:
        """today_time_display ウィジェットを取得する。"""
        return self.w.today_time_display

    def _refresh_overlay_time(self) -> None:
        """オーバーレイの時刻表示を更新する."""
        self._get_overlay_controller().refresh_overlay_time()

    def _sync_overlay_geometry(self) -> None:
        """オーバーレイを today_time_display の位置とサイズに追従させる."""
        self._get_overlay_controller().sync_overlay_geometry()

    # ----- Win32 ヘルパーへのデリゲーション -----

    @staticmethod
    def _global_rect_of_widget(widget: QWidget) -> Optional[Rect]:
        return global_rect_of_widget(widget)

    @staticmethod
    def _window_rect(hwnd: int) -> Optional[Rect]:
        return window_rect(hwnd)

    @staticmethod
    def _rect_contains_point(rect: Rect, x: int, y: int) -> bool:
        return rect_contains_point(rect, x, y)

    @staticmethod
    def _rects_intersect(first_rect: Rect, second_rect: Rect) -> bool:
        return rects_intersect(first_rect, second_rect)

    @staticmethod
    def _sample_points_from_rect(rect: Rect) -> List[Point]:
        return sample_points_from_rect(rect, OVERLAY_SAMPLE_RATIOS)

    @staticmethod
    def _window_at_point(x: int, y: int) -> int:
        return window_at_point(x, y)

    @staticmethod
    def _window_below(hwnd: int) -> int:
        return window_below(hwnd)

    @staticmethod
    def _root_window(hwnd: int) -> int:
        return root_window(hwnd)

    @staticmethod
    def _window_handle_of(widget: Optional[QWidget]) -> int:
        return window_handle_of(widget)

    def _is_own_window(self, hwnd: int) -> bool:
        """指定HWNDがMainWindowまたはオーバーレイ自身か判定する."""
        if hwnd == 0:
            return False
        if is_own_process_window(hwnd):
            return True
        hwnd_root = root_window(hwnd)
        main_hwnd = root_window(window_handle_of(self))
        overlay_hwnd = root_window(window_handle_of(self.overlay_window))
        return hwnd_root in {main_hwnd, overlay_hwnd}

    def _native_scale_factor(self) -> float:
        """Qt論理座標 -> Win32物理解像度座標へのスケールを推定する."""
        hwnd = window_handle_of(self)
        rect = window_rect(hwnd)
        logical_w = self.width()
        logical_h = self.height()
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
        foreground_hwnd = get_foreground_hwnd()
        if foreground_hwnd == 0 or self._is_own_window(foreground_hwnd):
            return None
        return self._window_rect(foreground_hwnd)

    def _find_covering_foreign_window_at_point(
        self,
        x: int,
        y: int,
        *,
        expected_root_hwnd: Optional[int] = None,
    ) -> int:
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
                    if expected_root_hwnd is not None:
                        candidate_root = self._root_window(hwnd)
                        if candidate_root != expected_root_hwnd:
                            hwnd = self._window_below(hwnd)
                            walk_count += 1
                            continue
                    return hwnd
            hwnd = self._window_below(hwnd)
            walk_count += 1

        if walk_count >= MAX_Z_WALK:
            logger.debug("overlay z-order walk reached MAX_Z_WALK=%s", MAX_Z_WALK)
        return 0

    def _get_today_display_cover_state(self) -> Tuple[bool, str]:
        """today_time_displayの被覆判定結果と理由を返す."""
        target = self._get_today_time_display()
        if target is None:
            return False, "target_missing"

        target_rect = self._global_rect_of_widget(target)
        if target_rect is None:
            return False, "target_rect_missing"

        # 前面ウィンドウの外接矩形が対象領域と交差しない場合は未被覆扱いにする。
        foreground_rect = self._foreground_rect_if_foreign()
        if foreground_rect is None:
            return False, "foreground_not_foreign"
        foreground_hwnd = get_foreground_hwnd()
        if foreground_hwnd == 0:
            return False, "foreground_not_foreign"
        foreground_root_hwnd = self._root_window(foreground_hwnd)
        if foreground_root_hwnd == 0:
            return False, "foreground_root_missing"

        sample_points = self._sample_points_from_rect(target_rect)

        def count_covering_foreign_points(*, use_native_points: bool) -> int:
            return sum(
                1
                for x, y in sample_points
                if self._find_covering_foreign_window_at_point(
                    *(self._to_native_point(x, y) if use_native_points else (x, y)),
                    expected_root_hwnd=foreground_root_hwnd,
                ) != 0
            )

        target_rect_native = self._to_native_rect(target_rect)
        if self._rects_intersect(target_rect_native, foreground_rect):
            covered_points = count_covering_foreign_points(use_native_points=True)
            if covered_points >= OVERLAY_COVERED_POINTS_THRESHOLD:
                return True, "covered_native_points"
            if covered_points > 0:
                return False, "covered_native_points_below_threshold"

        return False, "no_cover_detected"

    def _is_today_display_covered_by_foreground_window(self) -> bool:
        """today_time_displayのサンプル点が他ウィンドウに覆われているか判定する."""
        covered, _ = self._get_today_display_cover_state()
        return covered

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

    def _set_widget_with_height(
            self,
            widget: QWidget,
            visible: bool,
            *,
            min_height: int,
            max_height: int) -> None:
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
        self.display_mode = self._get_display_controller().next_display_mode(
            self.display_mode
        )
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
    configure_logging()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
