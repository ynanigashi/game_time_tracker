"""Mutable title-filter UI state for ReportDialog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReportTitleFilterState:
    """Tracks title-filter signal and initialization state."""

    updating: bool = False
    initialized: bool = False
