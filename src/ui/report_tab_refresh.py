"""Lazy refresh state for ReportDialog tabs."""

from __future__ import annotations

from src.ui.report_tab_state import ReportTabState


class ReportTabRefreshController:
    """Tracks loaded/dirty tabs and refreshes only the needed tab."""

    def __init__(
        self,
        owner: "ReportDialog",
        state: ReportTabState,
        *,
        summary_tab: int,
        trend_tab: int,
        log_tab: int,
    ) -> None:
        self.owner = owner
        self.state = state
        self.summary_tab = int(summary_tab)
        self.trend_tab = int(trend_tab)
        self.log_tab = int(log_tab)

    def refresh(self, *, force: bool = True) -> None:
        self.mark_all_tabs_dirty()
        self.refresh_current_tab(force=force)

    def current_tab_index(self) -> int:
        tabs = getattr(self.owner, "tabs", None)
        current_index = getattr(tabs, "currentIndex", None)
        if callable(current_index):
            return int(current_index())
        return self.summary_tab

    def mark_tab_dirty(self, tab_index: int) -> None:
        self.state.mark_tab_dirty(tab_index)

    def mark_tab_clean(self, tab_index: int) -> None:
        self.state.mark_tab_clean(
            tab_index,
            trend_tab=self.trend_tab,
        )

    def mark_all_tabs_dirty(self) -> None:
        self.state.mark_all_dirty({self.summary_tab, self.trend_tab, self.log_tab})

    def mark_report_data_changed(self) -> None:
        self.mark_all_tabs_dirty()
        self.state.reset_cached_report_data()

    def ensure_refresh_state(self) -> None:
        return None

    def refresh_current_tab(self, *, force: bool = False) -> None:
        self.refresh_tab(self.current_tab_index(), force=force)

    def refresh_tab(self, tab_index: int, *, force: bool = False) -> None:
        if (
            not force
            and tab_index in self.state.loaded_tabs
            and tab_index not in self.state.dirty_tabs
        ):
            return

        if tab_index == self.summary_tab:
            self.owner.refresh_summary()
        elif tab_index == self.trend_tab:
            self.owner.refresh_trend_tab()
        elif tab_index == self.log_tab:
            self.owner.refresh_logs()
        else:
            return
        self.mark_tab_clean(tab_index)

    def on_tab_changed(self, tab_index: int) -> None:
        self.refresh_tab(tab_index)
