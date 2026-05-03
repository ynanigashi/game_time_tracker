"""Compatibility exports for legacy MainWindow component imports.

New code should import overlay classes from ``src.app.main_overlay``.
"""

from src.app.main_overlay import (
    MainWindowOverlayController,
    TodayTimeOverlayWindow,
    _WinMsg,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MOUSEMOVE,
    MK_LBUTTON,
    QCursor,
    sys,
)

__all__ = [
    "MainWindowOverlayController",
    "TodayTimeOverlayWindow",
    "_WinMsg",
    "WM_LBUTTONDOWN",
    "WM_LBUTTONUP",
    "WM_MOUSEMOVE",
    "MK_LBUTTON",
    "QCursor",
    "sys",
]
