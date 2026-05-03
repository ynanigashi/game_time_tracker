"""Title-filter controller for the report dialog."""

from __future__ import annotations

from time import perf_counter
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from src.core.reporting import ReportSummary, build_game_report


class ReportTitleFilterController:
    """Manage title-filter checkboxes and refresh side effects."""

    def __init__(self, owner: object) -> None:
        self.owner = owner

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
        state = self.owner._ensure_report_tab_state()
        if (
            state.title_filter_summary is not None
            and not state.title_filter_dirty
        ):
            return state.title_filter_summary

        get_report_stats = getattr(self.owner.log_handler, "get_report_stats", None)
        if callable(get_report_stats):
            summary = get_report_stats(start_date=None, end_date=None)
        else:
            summary = build_game_report(self.owner._cached_records())
        state.title_filter_summary = summary
        return summary

    def sync_title_filter(self, summary: ReportSummary) -> None:
        checked_titles = (
            set(self.owner._selected_titles())
            if self.owner._title_filter_initialized
            else {row.game_title for row in summary.rows}
        )
        table = self.owner.title_filter_table
        self.owner._updating_title_filter = True
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
            self.owner._updating_title_filter = False
            self.owner._title_filter_initialized = True
            self.update_action_states()

    def on_title_filter_changed(self, *_args: object) -> None:
        if self.owner._updating_title_filter:
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
        self.owner._updating_title_filter = True
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
            self.owner._updating_title_filter = False

        self.update_action_states()
        self.owner.refresh_trend()
        self.owner._mark_tab_clean(self.owner._TREND_TAB)
        elapsed_ms = (perf_counter() - started_at) * 1000
        action = "全選択" if checked else "全解除"
        self.owner._set_debug_message(f"タイトルを{action} ({elapsed_ms:.0f} ms)")
