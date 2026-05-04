"""Shared composition helpers for MainWindow collaborators."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.app.main import MainWindow
    from src.app.main_window.action_methods import MainWindowActions
    from src.app.main_window.controller_methods import MainWindowControllerRegistry
    from src.app.main_window.scan_methods import MainWindowScanOps
    from src.app.main_window.state_descriptors import MainWindowStateAccess
    from src.app.main_window.tray_title_methods import MainWindowTrayTitleOps
    from src.app.main_window.win32_methods import MainWindowWin32Ops


class MainWindowCollaborator:
    """Base object for explicit MainWindow collaborators."""

    def __init__(self, owner: "MainWindow") -> None:
        object.__setattr__(self, "_owner", owner)

    @property
    def _state(self) -> "MainWindowStateAccess":
        return self._owner._state_access

    @property
    def _controllers(self) -> "MainWindowControllerRegistry":
        return self._owner._controllers

    @property
    def _actions(self) -> "MainWindowActions":
        return self._owner._actions

    @property
    def _scan_ops(self) -> "MainWindowScanOps":
        return self._owner._scan_ops

    @property
    def _tray_title_ops(self) -> "MainWindowTrayTitleOps":
        return self._owner._tray_title_ops

    @property
    def _win32_ops(self) -> "MainWindowWin32Ops":
        return self._owner._win32_ops
