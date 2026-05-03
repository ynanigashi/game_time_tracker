"""Mutable timer references for MainWindow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TimerState:
    """Owns background timer references so they are not garbage-collected."""

    scan_timer: Optional[Any] = None
    ui_timer: Optional[Any] = None
