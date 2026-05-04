"""Mutable trend selection state for ReportDialog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ReportTrendSelectionState:
    """Tracks the selected trend point index range."""

    selected_indices: Optional[Tuple[int, int]] = None
