"""Summary table helpers for the report dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QTableWidgetItem

from src.core.reporting import ReportSummary
from src.core.time_utils import format_hms


def summary_label_text(summary: ReportSummary) -> str:
    return (
        f"合計 {format_hms(summary.total_seconds)} / "
        f"{summary.session_count} 回 / {len(summary.rows)} ゲーム"
    )


class ReportSummaryTableController:
    """Populate the game summary label and table."""

    def __init__(self, owner: object) -> None:
        self.owner = owner

    def populate_summary(self, summary: ReportSummary) -> None:
        self.owner.summary_label.setText(summary_label_text(summary))
        self.populate_table(summary)

    def populate_table(self, summary: ReportSummary) -> None:
        table = self.owner.table
        table.setRowCount(len(summary.rows))
        for row_index, row in enumerate(summary.rows):
            last_played = (
                row.last_played.strftime("%Y/%m/%d %H:%M")
                if row.last_played is not None
                else "-"
            )
            table.setItem(row_index, 0, QTableWidgetItem(""))
            table.setCellWidget(
                row_index,
                0,
                self.owner._create_color_swatch(row.game_title),
            )

            values = [
                row.game_title,
                format_hms(row.total_seconds),
                str(row.session_count),
                format_hms(row.average_seconds),
                last_played,
            ]
            for column, value in enumerate(values):
                table.setItem(row_index, column + 1, QTableWidgetItem(value))
