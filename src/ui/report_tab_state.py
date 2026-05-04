"""Mutable refresh/cache state for ReportDialog tabs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.reporting import ReportSummary, TrendSeries


@dataclass
class ReportTabState:
    """Loaded/dirty tab state and cached report data."""

    loaded_tabs: Set[int] = field(default_factory=set)
    dirty_tabs: Set[int] = field(default_factory=set)
    title_filter_dirty: bool = True
    last_summary: Optional["ReportSummary"] = None
    title_filter_summary: Optional["ReportSummary"] = None
    last_trend_series: Optional[List["TrendSeries"]] = None

    def mark_tab_dirty(self, tab_index: int) -> None:
        self.dirty_tabs.add(tab_index)

    def mark_tab_clean(self, tab_index: int, *, trend_tab: int) -> None:
        self.loaded_tabs.add(tab_index)
        self.dirty_tabs.discard(tab_index)
        if tab_index == trend_tab:
            self.title_filter_dirty = False

    def mark_all_dirty(self, tab_indices: set[int]) -> None:
        self.dirty_tabs.update(tab_indices)
        self.title_filter_dirty = True

    def reset_cached_report_data(self) -> None:
        self.last_summary = None
        self.title_filter_summary = None
        self.last_trend_series = None
