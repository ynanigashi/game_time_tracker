"""Game Time Tracker - PySide6 GUI."""

import logging
import sys
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, TypeVar, cast

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QWidget,
)

from src.app.controllers import (
    BootstrapDependencies,
    MainWindowBootstrapError,
    MainWindowBootstrapResult,
    MainWindowBootstrapper,
    MainWindowContextMenuController,
    MainWindowDialogController,
    MainWindowDisplayController,
    MainWindowLoopController,
    MainWindowOverlayController,
    MainWindowOvertimeAlertController,
    MainWindowScanController,
    MainWindowStateController,
    MainWindowTitleController,
    MainWindowTrayController,
    MainWindowUiController,
    OvertimeAlertTracker,
    TodayTimeOverlayWindow,
)
from src.app.alert_state import GameAlertState
from src.app.cover_detector import CoverDetectorOps, Win32CoverDetector
from src.app.dialog_state import DialogRefState
from src.app.display_state import WindowDisplayState
from src.app.lifecycle_state import AppLifecycleState
from src.app.main_constants import (
    BASE_TITLE,
    INACTIVE_TIMEOUT_MINUTES,
    MAX_WIDGET_HEIGHT,
    MIN_MODE_SAFE_HEIGHT,
    MIN_MODE_SAFE_WIDTH,
    OVERLAY_COVERED_POINTS_THRESHOLD,
    OVERLAY_SAMPLE_RATIOS,
    OVERTIME_ALERT_THRESHOLDS_MINUTES,
    POLL_INTERVAL_SECONDS,
    UI_REFRESH_INTERVAL_SECONDS,
)
from src.app.main_scan_actions import MainWindowScanActions
from src.app.main_state_accessors import MainWindowStateAccessors
from src.app.main_tray_title_actions import MainWindowTrayTitleActions
from src.app.main_win32 import MainWindowWin32Mixin
from src.app.session_state import GameSessionState
from src.app.timer_state import TimerState
from src.app.tray_state import TrayActionState
from src.app.window_title_state import WindowTitleState
from src.app.win32_helpers import (
    get_foreground_hwnd,
    global_rect_of_widget,
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
from src.core.adapters import (
    GameInfoLoader,
    Messages,
    MIN_PLAY_MINUTES,
    SessionRecorder,
    WindowScanner,
)
from src.core.domain import DailyStatsTracker, GameStateTracker, ScanResult
from src.core.time_utils import SECONDS_PER_MINUTE
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
from src.infra.log_config import (
    DEFAULT_LOGGING_STATE,
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    configure_logging as configure_app_logging,
)
from src.infra.runtime_paths import (
    resolve_window_state_file,
)
from src.ui.gui_layout import build_main_layout
from src.ui.game_catalog_dialog import GameCatalogDialog
from src.ui.manual_record_dialog import ManualPlayRecord, ManualRecordDialog
from src.ui.report_dialog import ReportDialog
from src.ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)

LOG_FILE_PATH = DEFAULT_LOGGING_STATE.log_file_path
LOG_DIR = DEFAULT_LOGGING_STATE.log_dir


def configure_logging() -> None:
    """アプリ起動時にロギングを初期化する（import時は実行しない）。"""
    global LOG_DIR, LOG_FILE_PATH
    configure_app_logging(DEFAULT_LOGGING_STATE)
    LOG_FILE_PATH = DEFAULT_LOGGING_STATE.log_file_path
    LOG_DIR = DEFAULT_LOGGING_STATE.log_dir


TDependency = TypeVar("TDependency")


class MainWindow(
    QWidget,
    MainWindowScanActions,
    MainWindowStateAccessors,
    MainWindowTrayTitleActions,
    MainWindowWin32Mixin,
):
    """メインウィンドウ."""

    def __init__(self) -> None:
        super().__init__()
        self._initialize_window_state()
        self.w = build_main_layout(self)
        self._initialize_runtime_state()
        self._initialize_tray_icon()
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
        state_controller = self._get_state_controller()
        self.startup_window_visible = state_controller.load_startup_window_visible()
        self.tray_overlay_enabled = state_controller.load_tray_overlay_enabled()
        self.overlay_position = state_controller.load_overlay_position()
        self.setGeometry(x, y, *self.mode_sizes[self.display_mode])

    def _initialize_runtime_state(self) -> None:
        """実行時状態の初期値を設定する."""
        self.session_state = GameSessionState()
        self.browsers: Sequence[str] = DEFAULT_BROWSERS
        self.scanner: WindowScanner
        self.recorder: SessionRecorder
        self.daily_stats = DailyStatsTracker()
        self.overlay_window: Optional[TodayTimeOverlayWindow] = None
        self.tray_icon: Optional[object] = None
        self.tray_menu: Optional[QMenu] = None
        self.timer_state = TimerState()
        self.tray_action_state = TrayActionState()
        self.lifecycle_state = AppLifecycleState()
        current_display_mode = getattr(self, "display_mode", "max")
        current_mode_sizes = getattr(self, "mode_sizes", MODE_DEFAULT_SIZES)
        current_startup_window_visible = bool(
            getattr(self, "startup_window_visible", False)
        )
        current_tray_overlay_enabled = bool(
            getattr(self, "tray_overlay_enabled", False)
        )
        current_overlay_position = getattr(self, "overlay_position", None)
        self.display_state = WindowDisplayState.create(
            display_mode=current_display_mode,
            mode_sizes=current_mode_sizes,
            startup_window_visible=current_startup_window_visible,
            tray_overlay_enabled=current_tray_overlay_enabled,
            overlay_position=current_overlay_position,
        )
        current_overtime_alert_enabled = bool(
            getattr(self, "overtime_alert_enabled", DEFAULT_OVERTIME_ALERT_ENABLED)
        )
        self.alert_state = GameAlertState.create(
            enabled=current_overtime_alert_enabled,
            thresholds_minutes=OVERTIME_ALERT_THRESHOLDS_MINUTES,
        )
        self.dialog_state = DialogRefState()
        self.window_title_state = WindowTitleState()

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
        if not bool(getattr(self, "_is_quitting", True)):
            self._hide_main_window_to_tray()
            ignore = getattr(event, "ignore", None)
            if callable(ignore):
                ignore()
            return

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
                dependencies=BootstrapDependencies(
                    config_loader_cls=ConfigLoader,
                    game_info_loader_cls=GameInfoLoader,
                    window_scanner_cls=WindowScanner,
                    log_handler_cls=LogHandler,
                    session_recorder_cls=SessionRecorder,
                    game_state_tracker_cls=GameStateTracker,
                ),
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
            factory=lambda: MainWindowOverlayController(
                overlay_window_provider=lambda: self._get_overlay_window(),
                set_overlay_window=lambda window: setattr(
                    self,
                    "overlay_window",
                    window,
                ),
                set_overlay_position=lambda position: setattr(
                    self,
                    "overlay_position",
                    position,
                ),
                get_overlay_position=lambda: self.overlay_position,
                today_time_display_provider=lambda: self._get_today_time_display(),
                save_window_state=lambda: self._save_window_state(),
                has_playing_games=lambda: self._has_playing_games(),
                today_display_cover_state=lambda: self._get_today_display_cover_state(),
                is_own_window=lambda hwnd: self._is_own_window(hwnd),
                is_main_window_visible=lambda: bool(
                    getattr(self, "isVisible", lambda: False)()
                ),
                is_main_window_active=lambda: bool(
                    getattr(self, "isActiveWindow", lambda: False)()
                ),
                is_active_window_own=lambda active_window: active_window is self,
                window_geometry=self.geometry,
                move_window=self.move,
                get_tray_overlay_enabled=lambda: bool(self.tray_overlay_enabled),
            ),
            validator=lambda controller: (
                getattr(controller.window_geometry, "__self__", None) is self
                and getattr(controller.move_window, "__self__", None) is self
            ),
        )

    def _get_tray_controller(self) -> MainWindowTrayController:
        """Return the task-tray controller."""
        return self._resolve_dependency(
            "_tray_controller",
            factory=lambda: MainWindowTrayController(
                parent_widget=self,
                base_title=BASE_TITLE,
                action_state=self._ensure_tray_action_state(),
                get_tray_overlay_enabled=lambda: bool(self.tray_overlay_enabled),
                set_tray_overlay_enabled_value=lambda enabled: setattr(
                    self,
                    "tray_overlay_enabled",
                    bool(enabled),
                ),
                get_startup_window_visible=lambda: bool(self.startup_window_visible),
                set_startup_window_visible_value=lambda visible: setattr(
                    self,
                    "startup_window_visible",
                    bool(visible),
                ),
                get_force_startup_window_visible=lambda: bool(
                    self._force_startup_window_visible
                ),
                get_overlay_position=lambda: self.overlay_position,
                get_tray_icon=lambda: getattr(self, "tray_icon", None),
                set_tray_icon=lambda icon: setattr(self, "tray_icon", icon),
                set_tray_menu=lambda menu: setattr(self, "tray_menu", menu),
                show_window=self.show,
                hide_window=self.hide,
                raise_window=self.raise_,
                activate_window=self.activateWindow,
                is_window_visible=lambda: bool(self.isVisible()),
                window_geometry=self.geometry,
                move_window=self.move,
                open_manual_record_dialog=self._open_manual_record_dialog,
                open_report_dialog=self._open_report_dialog,
                open_game_catalog_dialog=self._open_game_catalog_dialog,
                open_settings_dialog=self._open_settings_dialog,
                sync_tray_window_actions_callback=self._sync_tray_window_actions,
                save_window_state=self._save_window_state,
                sync_overlay=self._sync_overlay,
                set_force_startup_window_visible=lambda visible: setattr(
                    self,
                    "_force_startup_window_visible",
                    bool(visible),
                ),
                process_pending_ui_events_callback=self._process_pending_ui_events,
                align_today_display_to_overlay_position_callback=(
                    self._align_today_display_to_overlay_position
                ),
                today_time_display_provider=self._get_today_time_display,
                set_quitting=lambda quitting: setattr(
                    self,
                    "_is_quitting",
                    bool(quitting),
                ),
                record_playing_games_before_close=(
                    self._record_playing_games_before_close
                ),
                close_overlay=self._close_overlay,
            ),
            validator=lambda controller: (
                controller.parent_widget is self
                and controller.action_state is self._ensure_tray_action_state()
            ),
        )

    def _get_dialog_controller(self) -> MainWindowDialogController:
        """Return the dialog orchestration controller."""
        return self._resolve_dependency(
            "_dialog_controller",
            factory=lambda: MainWindowDialogController(
                parent_widget=self,
                report_dialog_cls=ReportDialog,
                manual_record_dialog_cls=ManualRecordDialog,
                game_catalog_dialog_cls=GameCatalogDialog,
                settings_dialog_cls=SettingsDialog,
                state=self._ensure_dialog_state(),
                has_recorder=lambda: hasattr(self, "recorder"),
                log_handler_provider=lambda: self.recorder.log_handler,
                record_with_times=lambda game, start_time, end_time: (
                    self.recorder.record_with_times(game, start_time, end_time)
                ),
                games_provider=lambda: self.games,
                get_today_stats=lambda: self.recorder.log_handler.get_today_stats(),
                set_today_stats=self._set_today_stats_cache,
                set_disabled=lambda disabled: self.setDisabled(disabled),
                get_report_button=self._get_report_button,
                get_manual_record_button=self._get_manual_record_button,
                open_report_dialog_callback=self._open_report_dialog,
                open_manual_record_dialog_callback=self._open_manual_record_dialog,
                set_status=self._set_status,
                active_games_provider=lambda: self.active_games_cache,
                update_today_totals=self._update_today_totals,
                update_today_games_list=self._update_today_games_list,
                update_overtime_alert=self._update_overtime_alert,
                sync_overlay=self._sync_overlay,
                on_settings_saved_callback=self._on_settings_saved,
                on_game_catalog_saved_callback=self._on_game_catalog_saved,
                init_components=self._init_components,
            ),
            validator=lambda controller: (
                controller.parent_widget is self
                and controller.state is self._ensure_dialog_state()
            ),
        )

    def _get_context_menu_controller(self) -> MainWindowContextMenuController:
        """Return the right-click context-menu controller."""
        return self._resolve_dependency(
            "_context_menu_controller",
            factory=lambda: MainWindowContextMenuController(
                parent_widget=self,
                display_modes=DISPLAY_MODES,
                display_mode_provider=lambda: self.display_mode,
                set_display_mode=self._set_display_mode,
                open_manual_record_dialog=self._open_manual_record_dialog,
                open_report_dialog=self._open_report_dialog,
                open_game_catalog_dialog=self._open_game_catalog_dialog,
                open_settings_dialog=self._open_settings_dialog,
                quit_application=self._quit_application,
            ),
            validator=lambda controller: controller.parent_widget is self,
        )

    def _get_window_title_controller(self) -> MainWindowTitleController:
        """Return the current-window-title list controller."""
        return self._resolve_dependency(
            "_window_title_controller",
            factory=lambda: MainWindowTitleController(
                qmenu_cls=QMenu,
                state=self._ensure_window_title_state(),
                get_window_list_widget=lambda: getattr(self.w, "window_list", None),
                on_item_clicked=self._on_window_title_item_clicked,
                show_context_menu=self._show_window_title_context_menu,
                open_game_catalog_dialog=self._open_game_catalog_dialog,
                set_status=self._set_status,
            ),
            validator=lambda controller: (
                controller.state is self._ensure_window_title_state()
            ),
        )

    def _get_cover_detector(self) -> Win32CoverDetector:
        """Return the today-time display cover detector."""
        return self._resolve_dependency(
            "_cover_detector",
            factory=lambda: Win32CoverDetector(
                self,
                sample_ratios=OVERLAY_SAMPLE_RATIOS,
                covered_points_threshold=OVERLAY_COVERED_POINTS_THRESHOLD,
                target_widget_provider=self._get_today_time_display,
                ops=CoverDetectorOps(
                    root_window=lambda hwnd: self._root_window(hwnd),
                    window_handle_of=lambda widget: self._window_handle_of(widget),
                    window_rect=lambda hwnd: self._window_rect(hwnd),
                    rect_contains_point=lambda rect, x, y: self._rect_contains_point(
                        rect,
                        x,
                        y,
                    ),
                    rects_intersect=lambda first, second: self._rects_intersect(
                        first,
                        second,
                    ),
                    window_at_point=lambda x, y: self._window_at_point(x, y),
                    window_below=lambda hwnd: self._window_below(hwnd),
                    global_rect_of_widget=lambda widget: self._global_rect_of_widget(
                        widget
                    ),
                    sample_points_from_rect=lambda rect: self._sample_points_from_rect(
                        rect
                    ),
                ),
            ),
            validator=lambda detector: detector.owner is self,
        )

    def _get_scan_controller(self) -> MainWindowScanController:
        """Return the game scan controller."""
        return self._resolve_dependency(
            "_scan_controller",
            factory=lambda: MainWindowScanController(
                state_tracker=self.state_tracker,
                games_provider=lambda: self.games,
                scan_result_updater=lambda active, inactive, titles: (
                    self._ensure_session_state().update_scan_result(
                        active_games=active,
                        inactive_games=inactive,
                        window_titles=titles,
                    )
                ),
                update_active_list=self._update_active_list,
                update_window_list=self._update_window_list,
                update_scan_status=self._update_scan_status,
                set_status=self._set_status,
                load_today_game_minutes=self._load_today_game_minutes,
                get_today_stats=self.recorder.log_handler.get_today_stats,
            ),
            validator=lambda controller: (
                controller.state_tracker is self.state_tracker
            ),
        )

    def _get_overtime_alert_controller(self) -> MainWindowOvertimeAlertController:
        """Return the overtime-alert controller."""
        return self._resolve_dependency(
            "_overtime_alert_controller",
            factory=lambda: MainWindowOvertimeAlertController(
                self._ensure_alert_state(),
                toggle_provider=self._get_overtime_alert_toggle,
                on_toggle_changed=self._on_overtime_alert_toggled,
                active_games_provider=lambda: self.active_games_cache,
                inactive_games_provider=lambda: self.inactive_games_cache,
                calculate_today_total_seconds=lambda active, inactive, now: (
                    self._get_ui_controller().calculate_today_total_seconds(
                        active,
                        inactive,
                        now,
                    )
                ),
                sync_overlay=self._sync_overlay,
            ),
            validator=lambda controller: (
                controller.state is self._ensure_alert_state()
            ),
        )

    def _init_components(self) -> None:
        """設定を読み込みコンポーネントを初期化."""
        try:
            result = self._get_bootstrapper().bootstrap(window_title=self.windowTitle())
        except MainWindowBootstrapError as e:
            if e.log_message:
                logger.error(e.log_message)
            if getattr(e, "open_settings", False):
                self._force_startup_window_visible = True
                self._set_status(e.status_message)
                alert_message = getattr(e, "alert_message", None)
                if alert_message:
                    QMessageBox.warning(
                        self,
                        getattr(e, "alert_title", "設定エラー"),
                        alert_message,
                    )
                self._open_settings_dialog()
                return
            if getattr(e, "open_game_catalog", False):
                self._force_startup_window_visible = True
                self._set_status(e.status_message)
                self._open_game_catalog_dialog()
                return
            self._force_startup_window_visible = True
            self._disable_with_status(e.status_message)
            return

        self._apply_bootstrap_result(result)
        self._initialize_overtime_alert_toggle()
        self._initialize_report_button()
        self._initialize_manual_record_button()
        self._apply_display_mode()
        self._apply_mode_geometry()
        self._set_status(Messages.NO_GAME_PLAYING)
        self._initialize_overlay()

    def _save_window_state(self) -> None:
        """ウィンドウ位置・サイズ・表示モードを保存."""
        self._get_state_controller().save(
            self.geometry(),
            self.display_mode,
            self.mode_sizes,
            self._is_overtime_alert_enabled(),
            startup_window_visible=bool(getattr(self, "startup_window_visible", False)),
            tray_overlay_enabled=bool(getattr(self, "tray_overlay_enabled", False)),
            overlay_position=getattr(self, "overlay_position", None),
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
        """Return whether overtime alerts are enabled."""
        return self._get_overtime_alert_controller().is_enabled()

    def _set_overtime_alert_enabled(self, enabled: bool) -> None:
        """Set whether overtime alerts are enabled."""
        self._get_overtime_alert_controller().set_enabled(enabled)

    def _get_overtime_alert_tracker(self) -> OvertimeAlertTracker:
        """Return the overtime alert progress tracker."""
        return self._get_overtime_alert_controller().get_tracker()

    def _get_overtime_alert_toggle(self) -> Optional[QPushButton]:
        """時間超過防止アラートのトグルを取得する。"""
        return self.w.overtime_alert_toggle

    def _get_report_button(self) -> Optional[QPushButton]:
        """Return the report button when the layout provides one."""
        return getattr(self.w, "report_button", None)

    def _get_manual_record_button(self) -> Optional[QPushButton]:
        """Return the manual record button when the layout provides one."""
        return getattr(self.w, "manual_record_button", None)

    def _initialize_overtime_alert_toggle(self) -> None:
        """Initialize the overtime-alert toggle."""
        self._get_overtime_alert_controller().initialize_toggle()

    def _initialize_report_button(self) -> None:
        """Connect the report button to the report dialog."""
        self._get_dialog_controller().initialize_report_button()

    def _initialize_manual_record_button(self) -> None:
        """Connect the manual record button to the manual entry dialog."""
        self._get_dialog_controller().initialize_manual_record_button()

    def _open_report_dialog(self) -> None:
        """Open a non-modal report dialog backed by the cached log handler."""
        self._get_dialog_controller().open_report_dialog()

    def _open_manual_record_dialog(self) -> None:
        """Open a non-modal dialog for manually entering play time."""
        self._get_dialog_controller().open_manual_record_dialog()

    def _get_or_create_manual_record_dialog(self) -> ManualRecordDialog:
        """Return a manual record dialog refreshed with the current game list."""
        return cast(
            ManualRecordDialog,
            self._get_dialog_controller().get_or_create_manual_record_dialog(),
        )

    def _save_manual_record(self, record: ManualPlayRecord) -> bool:
        """Persist a manually entered session and refresh today's totals."""
        return self._get_dialog_controller().save_manual_record(record)

    def _refresh_after_manual_record(self) -> None:
        """Refresh cached stats, visible tables, alert progress, and overlay."""
        self._get_dialog_controller().refresh_after_manual_record()

    def _reload_today_stats(self) -> None:
        """Refresh cached completed play time from the log handler."""
        self._get_dialog_controller().reload_today_stats()

    def _set_today_stats_cache(
        self,
        game_minutes: Dict[str, float],
        completed_seconds: float,
    ) -> None:
        self.daily_stats.today_game_minutes_cache = game_minutes
        self.daily_stats.today_completed_seconds = completed_seconds
        self.daily_stats.last_today_games_content = ""

    def _open_settings_dialog(self) -> None:
        """Open a non-modal settings dialog."""
        self._get_dialog_controller().open_settings_dialog()

    def _open_game_catalog_dialog(self, *, initial_window_title: str = "") -> None:
        """Open a non-modal game catalog dialog."""
        self._get_dialog_controller().open_game_catalog_dialog(
            initial_window_title=initial_window_title
        )

    def _on_game_catalog_saved(self) -> None:
        """Reload runtime services after the game catalog changes."""
        self._get_dialog_controller().on_game_catalog_saved()

    def _on_settings_saved(self) -> None:
        """Reload runtime services after settings are saved."""
        self._get_dialog_controller().on_settings_saved()

    def _on_overtime_alert_toggled(self, checked: bool) -> None:
        """Handle overtime-alert toggle changes."""
        self._get_overtime_alert_controller().on_toggled(checked)

    def _prime_overtime_alert_progress(self, total_seconds: float) -> None:
        """Prime overtime-alert progress without emitting past thresholds."""
        self._get_overtime_alert_controller().prime_progress(total_seconds)

    def _emit_overtime_alert(self, threshold_minutes: int) -> None:
        """Emit an overtime-alert notification."""
        self._get_overtime_alert_controller().emit_alert(threshold_minutes)

    def _update_overtime_alert(self, total_seconds: float) -> None:
        """Check overtime thresholds and emit newly crossed alerts."""
        self._get_overtime_alert_controller().update_alert(total_seconds)

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
        if self._should_show_context_menu(event):
            self._show_context_menu(event)
            super().mousePressEvent(event)
            return
        if self._should_cycle_display_mode(event):
            self._cycle_display_mode()
        super().mousePressEvent(event)

    @staticmethod
    def _should_cycle_display_mode(event: QMouseEvent) -> bool:
        """表示モード切り替え対象のクリックかを判定."""
        return event.button() == Qt.MouseButton.LeftButton

    @staticmethod
    def _should_show_context_menu(event: QMouseEvent) -> bool:
        return event.button() == Qt.MouseButton.RightButton

    def _show_context_menu(self, event: QMouseEvent) -> None:
        self._get_context_menu_controller().show_context_menu(event)

    def _add_display_mode_menu(self, menu: QMenu) -> Dict[str, object]:
        return self._get_context_menu_controller().add_display_mode_menu(menu)

    def _handle_context_menu_selection(
        self,
        selected_action: object,
        *,
        report_action: object,
        settings_action: object,
        exit_action: object,
        game_catalog_action: object = None,
        mode_actions: Optional[Dict[str, object]] = None,
        manual_record_action: object = None,
    ) -> None:
        self._get_context_menu_controller().handle_context_menu_selection(
            selected_action,
            report_action=report_action,
            settings_action=settings_action,
            exit_action=exit_action,
            game_catalog_action=game_catalog_action,
            mode_actions=mode_actions,
            manual_record_action=manual_record_action,
        )

    def _set_display_mode(self, display_mode: str) -> None:
        if display_mode not in DISPLAY_MODES:
            return
        if self.display_mode == display_mode:
            return
        self.display_mode = display_mode
        self._apply_display_mode()
        self._save_window_state()

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
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    if window.should_show_window_on_startup():
        window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
