"""Game Time Tracker - PySide6 GUI."""

import logging
import sys
from datetime import datetime
from typing import Callable, Optional, Sequence, TypeVar, cast

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QWidget,
)

from src.app.controllers import (
    BootstrapDependencies,
    MainWindowBootstrapResult,
    MainWindowBootstrapper,
    OvertimeAlertTracker,
    TodayTimeOverlayWindow,
)
from src.app.alert_state import GameAlertState
from src.app.dialog_state import DialogRefState
from src.app.display_state import WindowDisplayState
from src.app.lifecycle_state import AppLifecycleState
from src.app.main_constants import (
    BASE_TITLE,
    INACTIVE_TIMEOUT_MINUTES,
    MIN_MODE_SAFE_HEIGHT,
    MIN_MODE_SAFE_WIDTH,
    OVERTIME_ALERT_THRESHOLDS_MINUTES,
    POLL_INTERVAL_SECONDS,
    UI_REFRESH_INTERVAL_SECONDS,
)
from src.app.main_window.legacy_aliases import method_aliases, state_aliases
from src.app.main_window.action_methods import MainWindowActions
from src.app.main_window.controller_methods import MainWindowControllerRegistry
from src.app.main_window.scan_methods import MainWindowScanOps
from src.app.main_window.state_descriptors import MainWindowStateAccess
from src.app.main_window.tray_title_methods import MainWindowTrayTitleOps
from src.app.main_window.win32_methods import MainWindowWin32Ops
from src.app.session_state import GameSessionState
from src.app.timer_state import TimerState
from src.app.tray_state import TrayActionState
from src.app.window_title_state import WindowTitleState
from src.app.win32_helpers import get_foreground_hwnd
from src.core.adapters import (
    GameInfoLoader,
    Messages,
    MIN_PLAY_MINUTES,
    SessionRecorder,
    WindowScanner,
)
from src.core.domain import DailyStatsTracker, GameStateTracker
from src.core.time_utils import SECONDS_PER_MINUTE
from src.core.window_state import (
    DEFAULT_OVERTIME_ALERT_ENABLED,
    DISPLAY_MODES,
    MODE_DEFAULT_SIZES,
)
from src.infra.config_loader import (
    ConfigLoader,
    DEFAULT_BROWSERS,
    DEFAULT_EXCLUDED_TITLES,
)
from src.infra.log_config import (
    DEFAULT_LOGGING_STATE,
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    configure_logging as configure_app_logging,
)
from src.infra.log_handler import LogHandler
from src.ui.gui_layout import build_main_layout

logger = logging.getLogger(__name__)

LOG_FILE_PATH = DEFAULT_LOGGING_STATE.log_file_path
LOG_DIR = DEFAULT_LOGGING_STATE.log_dir


def configure_logging() -> None:
    """Configure application logging at startup."""
    global LOG_DIR, LOG_FILE_PATH
    configure_app_logging(DEFAULT_LOGGING_STATE)
    LOG_FILE_PATH = DEFAULT_LOGGING_STATE.log_file_path
    LOG_DIR = DEFAULT_LOGGING_STATE.log_dir


TDependency = TypeVar("TDependency")


class MainWindow(QWidget):
    """Main application window."""

    locals().update(state_aliases())
    locals().update(method_aliases())

    def __init__(self) -> None:
        super().__init__()
        self._initialize_collaborators()
        self._initialize_window_state()
        self.w = build_main_layout(self)
        self._initialize_runtime_state()
        self._tray_title_ops._initialize_tray_icon()
        self._tray_title_ops._initialize_window_title_copy()
        self._warmup_dependencies()
        self._actions._init_components()
        self._start_background_timers()
        self._run_initial_refresh()

    def _initialize_collaborators(self) -> None:
        self._state_access = MainWindowStateAccess(self)
        self._controllers = MainWindowControllerRegistry(self)
        self._actions = MainWindowActions(self)
        self._scan_ops = MainWindowScanOps(self)
        self._tray_title_ops = MainWindowTrayTitleOps(self)
        self._win32_ops = MainWindowWin32Ops(self)

    def _initialize_window_state(self) -> None:
        """Apply the persisted window state."""
        self.setWindowTitle(BASE_TITLE)
        state = self._state_access
        (
            x,
            y,
            state.display_mode,
            state.mode_sizes,
            state.overtime_alert_enabled,
        ) = self._controllers._get_state_controller().load_all()
        state_controller = self._controllers._get_state_controller()
        state.startup_window_visible = state_controller.load_startup_window_visible()
        state.tray_overlay_enabled = state_controller.load_tray_overlay_enabled()
        state.overlay_position = state_controller.load_overlay_position()
        self.setGeometry(x, y, *state.mode_sizes[state.display_mode])

    def _initialize_runtime_state(self) -> None:
        """Initialize runtime-only state."""
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
        state = self._state_access
        current_display_mode = state.display_mode
        current_mode_sizes = state.mode_sizes
        current_startup_window_visible = bool(state.startup_window_visible)
        current_tray_overlay_enabled = bool(state.tray_overlay_enabled)
        current_overlay_position = state.overlay_position
        self.display_state = WindowDisplayState.create(
            display_mode=current_display_mode,
            mode_sizes=current_mode_sizes,
            startup_window_visible=current_startup_window_visible,
            tray_overlay_enabled=current_tray_overlay_enabled,
            overlay_position=current_overlay_position,
        )
        current_overtime_alert_enabled = bool(state.overtime_alert_enabled)
        self.alert_state = GameAlertState.create(
            enabled=current_overtime_alert_enabled,
            thresholds_minutes=OVERTIME_ALERT_THRESHOLDS_MINUTES,
        )
        self.dialog_state = DialogRefState()
        self.window_title_state = WindowTitleState()

    def _warmup_dependencies(self) -> None:
        """Create dependencies used immediately after startup."""
        self._controllers._get_ui_controller()
        self._controllers._get_display_controller()
        self._controllers._get_loop_controller()
        self._controllers._get_overlay_controller()
        self._get_bootstrapper()

    def _start_background_timers(self) -> None:
        """Start background refresh timers."""
        # Keep timer objects alive to prevent garbage collection.
        self._state_access._scan_timer = self._start_timer(
            POLL_INTERVAL_SECONDS,
            self._scan_tick,
        )
        self._state_access._ui_timer = self._start_timer(
            UI_REFRESH_INTERVAL_SECONDS,
            self._ui_tick,
        )

    def _run_initial_refresh(self) -> None:
        """Run the first scan and UI refresh."""
        self._scan_tick()
        self._ui_tick()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Hide to tray or save state before application exit."""
        if not bool(self._is_quitting):
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
        """Return a DailyStatsTracker instance."""
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
        """Resolve and cache a dependency."""
        dependency = cast(Optional[TDependency], getattr(self, attr_name, None))
        if dependency is None or (validator is not None and not validator(dependency)):
            dependency = factory()
            setattr(self, attr_name, dependency)
        return dependency

    def _get_bootstrapper(self) -> MainWindowBootstrapper:
        """Return the bootstrapper for startup dependencies."""
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
        """Apply bootstrap results to MainWindow state."""
        self._state_access.games = result.games
        self.browsers = result.browsers
        self.scanner = result.scanner
        self.recorder = result.recorder
        self.state_tracker = result.state_tracker
        self.daily_stats.today_game_minutes_cache = result.today_game_minutes
        self.daily_stats.today_completed_seconds = result.today_completed_seconds

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse clicks for context menu and display mode cycling."""
        if self._should_show_context_menu(event):
            self._show_context_menu(event)
            super().mousePressEvent(event)
            return
        if self._should_cycle_display_mode(event):
            self._cycle_display_mode()
        super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Record the current mode size on resize."""
        self._record_current_mode_size()
        super().resizeEvent(event)

    def _ui_tick(self) -> None:
        """Refresh displayed play time and overlay state."""
        now = datetime.now()
        active_games = self._state_access.active_games_cache
        self._update_session_times(active_games, now)
        total_seconds = self._update_today_totals(active_games, now)
        self._update_today_games_list(now)
        self._update_overtime_alert(total_seconds)
        self._sync_overlay()


def main() -> None:
    configure_logging()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    if window._tray_title_ops.should_show_window_on_startup():
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
