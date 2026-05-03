"""Mutable graph unit toggle state for ReportDialog."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class ReportGraphUnitState:
    """Tracks minute/hour unit selection and toggle widgets."""

    graph_unit_hours: bool = False
    updating_unit_toggles: bool = False
    minute_buttons: List[Any] = field(default_factory=list)
    hour_buttons: List[Any] = field(default_factory=list)
