"""Mutable overlay controller state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class OverlayVisibilityLogState:
    """Tracks the last logged overlay visibility state."""

    last_should_show: Optional[bool] = None
    last_reason: Optional[str] = None
    last_log_monotonic: float = 0.0
