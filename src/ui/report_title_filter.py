"""Title-filter controller for the report dialog."""

from __future__ import annotations

from time import perf_counter
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from src.core.reporting import ReportSummary, build_game_report
from src.ui.report_tab_state import ReportTabState
from src.ui.report_title_filter_state import ReportTitleFilterState


class ReportTitleFilterController:
    """Manage title-filter checkboxes and refresh side effects."""

    def __init__(
        self,
        owner: object,
        state: ReportTitleFilterState,
        tab_state: ReportTabState,
        *,
        trend_tab: int,
    ) -> None:
        self.owner = owner
        self.state = state
        self.tab_state = tab_state
        self.trend_tab = int(trend_tab)

    def selected_titles(self) -> List[str]:
        titles: List[str] = []
        table = self.owner.title_filter_table
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                titles.append(item.text())
        return titles

    def load_title_filter_summary(self) -> ReportSummary:
        if (
            self.tab_state.title_filter_summary is not None
            and not self.tab_state.title_filter_dirty
        ):
            return self.tab_state.title_filter_summary

        get_report_stats = getattr(self.owner.log_handler, "get_report_stats", None)
        if callable(get_report_stats):
            summary = get_report_stats(start_date=None, end_date=None)
        else:
            summary = build_game_report(self.owner._cached_records())
        self.tab_state.title_filter_summary = summary
        return summary

    def sync_title_filter(self, summary: ReportSummary) -> None:
        checked_titles = (
            set(self.selected_titles())
            if self.state.initialized
            else {row.game_title for row in summary.rows}
        )
        table = self.owner.title_filter_table
        self.state.updating = True
        table.blockSignals(True)
        try:
            table.setRowCount(len(summary.rows))
            for row_index, row in enumerate(summary.rows):
                item = QTableWidgetItem(row.game_title)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if row.game_title in checked_titles
                    else Qt.CheckState.Unchecked
                )
                table.setItem(row_index, 0, item)
        finally:
            table.blockSignals(False)
            self.state.updating = False
            self.state.initialized = True
            self.update_action_states()

    def on_title_filter_changed(self, *_args: object) -> None:
        if self.state.updating:
            return
        if not self.owner._is_title_trend_mode():
            self.update_action_states()
            return
        self.owner.refresh_trend()
        self.update_action_states()

    def title_filter_counts(self) -> Tuple[int, int]:
        table = self.owner.title_filter_table
        total_count = table.rowCount()
        checked_count = 0
        for row in range(total_count):
            item = table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                checked_count += 1
        return total_count, checked_count

    def update_action_states(self) -> None:
        title_mode = self.owner._is_title_trend_mode()
        self.owner.title_filter_label.setEnabled(title_mode)
        self.owner.title_filter_table.setEnabled(title_mode)
        total_count, checked_count = self.title_filter_counts()
        self.owner.select_all_titles_button.setEnabled(
            title_mode and total_count > 0 and checked_count < total_count
        )
        self.owner.clear_all_titles_button.setEnabled(
            title_mode and checked_count > 0
        )

    def set_all_title_filters(self, checked: bool) -> None:
        started_at = perf_counter()
        if not self.owner._is_title_trend_mode():
            self.owner._set_debug_message("合計表示ではタイトル選択は使用しません")
            self.update_action_states()
            return
        total_count, checked_count = self.title_filter_counts()
        if total_count == 0:
            self.owner._set_debug_message("タイトルがありません")
            self.update_action_states()
            return
        if checked and checked_count == total_count:
            self.owner._set_debug_message("タイトルはすでに全選択済みです")
            self.update_action_states()
            return
        if not checked and checked_count == 0:
            self.owner._set_debug_message("タイトルはすでに全解除済みです")
            self.update_action_states()
            return

        table = self.owner.title_filter_table
        self.state.updating = True
        table.blockSignals(True)
        try:
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item is not None:
                    item.setCheckState(
                        Qt.CheckState.Checked
                        if checked
                        else Qt.CheckState.Unchecked
                    )
        finally:
            table.blockSignals(False)
            self.state.updating = False

        self.update_action_states()
        self.owner.refresh_trend()
        self.owner._mark_tab_clean(self.trend_tab)
        elapsed_ms = (perf_counter() - started_at) * 1000
        action = "全選択" if checked else "全解除"
        self.owner._set_debug_message(f"タイトルを{action} ({elapsed_ms:.0f} ms)")
