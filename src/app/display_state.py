"""Mutable state for MainWindow display and tray presentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence, Tuple

from src.core.window_state import MODE_DEFAULT_SIZES


@dataclass
class WindowDisplayState:
    """Owns display-mode and tray presentation settings."""

    display_mode: str
    mode_sizes: Dict[str, Tuple[int, int]]
    startup_window_visible: bool
    tray_overlay_enabled: bool
    overlay_position: Optional[Tuple[int, int]]

    @classmethod
    def create(
        cls,
        *,
        display_mode: str = "max",
        mode_sizes: Optional[Mapping[str, Sequence[int]]] = None,
        startup_window_visible: bool = False,
        tray_overlay_enabled: bool = False,
        overlay_position: Optional[Sequence[int]] = None,
    ) -> "WindowDisplayState":
        return cls(
            display_mode=str(display_mode),
            mode_sizes=_coerce_mode_sizes(mode_sizes),
            startup_window_visible=bool(startup_window_visible),
            tray_overlay_enabled=bool(tray_overlay_enabled),
            overlay_position=_coerce_position(overlay_position),
        )


def _coerce_mode_sizes(
    mode_sizes: Optional[Mapping[str, Sequence[int]]],
) -> Dict[str, Tuple[int, int]]:
    source = mode_sizes or MODE_DEFAULT_SIZES
    return {
        str(mode): (int(size[0]), int(size[1]))
        for mode, size in source.items()
    }


def _coerce_position(position: Optional[Sequence[int]]) -> Optional[Tuple[int, int]]:
    if position is None:
        return None
    return (int(position[0]), int(position[1]))
