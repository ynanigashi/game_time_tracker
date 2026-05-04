"""Mutable connection state for the MainWindow title list."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WindowTitleState:
    """Tracks title-list signal connections."""

    copy_connected: bool = False
    context_menu_connected: bool = False
