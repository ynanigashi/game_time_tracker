"""Mutable lifecycle flags for MainWindow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppLifecycleState:
    """Tracks app quit and startup display override flags."""

    is_quitting: bool = False
    force_startup_window_visible: bool = False
