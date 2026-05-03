"""MainWindow controller exports.

This package is the stable import surface for MainWindow controllers while the
implementation files are kept in their existing locations.
"""

from src.app.main_alerts import MainWindowOvertimeAlertController, OvertimeAlertTracker
from src.app.main_bootstrap import (
    BootstrapDependencies,
    MainWindowBootstrapError,
    MainWindowBootstrapResult,
    MainWindowBootstrapper,
    NoGamesConfiguredError,
)
from src.app.main_context_menu import MainWindowContextMenuController
from src.app.main_dialogs import MainWindowDialogController
from src.app.main_loop import MainWindowLoopController
from src.app.main_overlay import MainWindowOverlayController, TodayTimeOverlayWindow
from src.app.main_scan import MainWindowScanController
from src.app.main_ui import MainWindowDisplayController, MainWindowUiController
from src.app.tray_controller import MainWindowTrayController
from src.app.window_state_controller import MainWindowStateController
from src.app.window_title_controller import MainWindowTitleController

__all__ = [
    "BootstrapDependencies",
    "MainWindowBootstrapError",
    "MainWindowBootstrapResult",
    "MainWindowBootstrapper",
    "MainWindowContextMenuController",
    "MainWindowDialogController",
    "MainWindowDisplayController",
    "MainWindowLoopController",
    "MainWindowOverlayController",
    "MainWindowOvertimeAlertController",
    "MainWindowScanController",
    "MainWindowStateController",
    "MainWindowTitleController",
    "MainWindowTrayController",
    "MainWindowUiController",
    "NoGamesConfiguredError",
    "OvertimeAlertTracker",
    "TodayTimeOverlayWindow",
]
