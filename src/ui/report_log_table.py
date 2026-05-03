"""Log table helpers for the report dialog."""

from __future__ import annotations

from typing import List

from PySide6.QtWidgets import QTableWidgetItem


def bool_text(value: object) -> str:
    return "TRUE" if value is True or str(value).upper() == "TRUE" else "FALSE"


class ReportLogTableController:
    """Populate the raw log table and mirror selection into edit fields."""

    def __init__(self, owner: object) -> None:
        self.owner = owner

    def populate_log_table(self, records: List[dict]) -> None:
        rows = sorted(
            records,
            key=lambda record: int(record.get("index") or 0),
            reverse=True,
        )
        self.owner.log_table.setRowCount(len(rows))
        for row_index, record in enumerate(rows):
            values = [
                str(record.get("record_id", "")),
                str(record.get("device_id", "")),
                str(record.get("index", "")),
                str(record.get("start_time", "")),
                str(record.get("end_time", "")),
                str(record.get("title", "")),
                bool_text(record.get("play_with_friends", False)),
            ]
            for column, value in enumerate(values):
                self.owner.log_table.setItem(row_index, column, QTableWidgetItem(value))

    def selected_log_row(self) -> int:
        row = self.owner.log_table.currentRow()
        return row if 0 <= row < self.owner.log_table.rowCount() else -1

    def log_table_text(self, row: int, column: int) -> str:
        item = self.owner.log_table.item(row, column)
        return item.text() if item is not None else ""

    def apply_selected_log_row(self) -> None:
        row = self.selected_log_row()
        if row < 0:
            self.owner.log_start_time_edit.setText("")
            self.owner.log_end_time_edit.setText("")
            self.owner.log_title_edit.setText("")
            self.owner.log_friends_check.setChecked(False)
            return
        self.owner.log_start_time_edit.setText(self.log_table_text(row, 3))
        self.owner.log_end_time_edit.setText(self.log_table_text(row, 4))
        self.owner.log_title_edit.setText(self.log_table_text(row, 5))
        self.owner.log_friends_check.setChecked(self.log_table_text(row, 6) == "TRUE")
