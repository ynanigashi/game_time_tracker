"""Lazy refresh state for ReportDialog tabs."""

from __future__ import annotations


class ReportTabRefreshController:
    """Tracks loaded/dirty tabs and refreshes only the needed tab."""

    def __init__(self, owner: "ReportDialog") -> None:
        self.owner = owner

    def refresh(self, *, force: bool = True) -> None:
        self.mark_all_tabs_dirty()
        self.refresh_current_tab(force=force)

    def current_tab_index(self) -> int:
        tabs = getattr(self.owner, "tabs", None)
        current_index = getattr(tabs, "currentIndex", None)
        if callable(current_index):
            return int(current_index())
        return self.owner._SUMMARY_TAB

    def mark_tab_dirty(self, tab_index: int) -> None:
        self.owner._ensure_report_tab_state().mark_tab_dirty(tab_index)

    def mark_tab_clean(self, tab_index: int) -> None:
        self.owner._ensure_report_tab_state().mark_tab_clean(
            tab_index,
            trend_tab=self.owner._TREND_TAB,
        )

    def mark_all_tabs_dirty(self) -> None:
        self.owner._ensure_report_tab_state().mark_all_dirty(
            {
                self.owner._SUMMARY_TAB,
                self.owner._TREND_TAB,
                self.owner._LOG_TAB,
            }
        )

    def mark_report_data_changed(self) -> None:
        self.mark_all_tabs_dirty()
        self.owner._ensure_report_tab_state().reset_cached_report_data()

    def ensure_refresh_state(self) -> None:
        self.owner._ensure_report_tab_state()

    def refresh_current_tab(self, *, force: bool = False) -> None:
        self.refresh_tab(self.current_tab_index(), force=force)

    def refresh_tab(self, tab_index: int, *, force: bool = False) -> None:
        state = self.owner._ensure_report_tab_state()
        if (
            not force
            and tab_index in state.loaded_tabs
            and tab_index not in state.dirty_tabs
        ):
            return

        if tab_index == self.owner._SUMMARY_TAB:
            self.owner.refresh_summary()
        elif tab_index == self.owner._TREND_TAB:
            self.owner.refresh_trend_tab()
        elif tab_index == self.owner._LOG_TAB:
            self.owner.refresh_logs()
        else:
            return
        self.mark_tab_clean(tab_index)

    def on_tab_changed(self, tab_index: int) -> None:
        self.refresh_tab(tab_index)
