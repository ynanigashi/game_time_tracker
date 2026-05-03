"""Mutable tray menu action references for MainWindow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TrayActionState:
    """Owns tray menu actions that need later synchronization."""

    show_action: Optional[Any] = None
    hide_action: Optional[Any] = None
    startup_show_action: Optional[Any] = None
    startup_hide_action: Optional[Any] = None
    overlay_action: Optional[Any] = None
