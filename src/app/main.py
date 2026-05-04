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
from src.app.main_action_methods import install_main_window_action_methods
from src.app.main_controller_methods import install_main_window_controller_methods
from src.app.main_scan_actions import install_main_window_scan_methods
from src.app.main_state_accessors import install_main_window_state_accessors
from src.app.main_tray_title_actions import install_main_window_tray_title_actions
from src.app.main_win32 import install_main_window_win32_methods
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


class MainWindow(QWidget):
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """クリックで表示モードをトグル。"""
        if self._should_show_context_menu(event):
            self._show_context_menu(event)
            super().mousePressEvent(event)
            return
        if self._should_cycle_display_mode(event):
            self._cycle_display_mode()
        super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """リサイズ時に現在モードのサイズを記録."""
        self._record_current_mode_size()
        super().resizeEvent(event)

    def _ui_tick(self) -> None:
        """UIだけを高速更新（0.1秒間隔）."""
        self._get_loop_controller().run_ui_tick(self)
        self._sync_overlay()


# =============================================================================
# エントリーポイント
# =============================================================================
install_main_window_state_accessors(MainWindow)
install_main_window_scan_methods(MainWindow)
install_main_window_tray_title_actions(MainWindow)
install_main_window_win32_methods(MainWindow)
install_main_window_controller_methods(MainWindow)
install_main_window_action_methods(MainWindow)


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
