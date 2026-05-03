"""Display mode sizing helpers."""

from __future__ import annotations

from typing import Tuple

MIN_MODE_SAFE_WIDTH = 320
MIN_MODE_SAFE_HEIGHT = 110


def clamp_mode_size(display_mode: str, width: int, height: int) -> Tuple[int, int]:
    """Ensure persisted min-mode sizes cannot hide essential controls."""
    if display_mode == "min":
        return max(width, MIN_MODE_SAFE_WIDTH), max(height, MIN_MODE_SAFE_HEIGHT)
    return width, height
