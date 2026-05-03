"""MainWindow controller exports.

This package is the stable import surface for MainWindow controllers.
"""

from src.app.controllers.bootstrap import (
    BootstrapDependencies,
    MainWindowBootstrapError,
    MainWindowBootstrapResult,
    MainWindowBootstrapper,
    NoGamesConfiguredError,
)
from src.app.controllers.context_menu import MainWindowContextMenuController
from src.app.controllers.dialog import MainWindowDialogController
from src.app.controllers.display import MainWindowDisplayController
from src.app.controllers.loop import MainWindowLoopController
from src.app.controllers.overlay import MainWindowOverlayController, TodayTimeOverlayWindow
from src.app.controllers.overtime_alert import (
    MainWindowOvertimeAlertController,
    OvertimeAlertTracker,
)
from src.app.controllers.scan import MainWindowScanController
from src.app.controllers.tray import MainWindowTrayController
from src.app.controllers.ui import MainWindowUiController
from src.app.controllers.window_state import MainWindowStateController
from src.app.controllers.window_title import MainWindowTitleController

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
