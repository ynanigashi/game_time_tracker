import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from tests.test_stubs import install_stubs

install_stubs()

from PySide6.QtWidgets import QLabel

from src.core.reporting import GameReportRow, ReportSummary
from src.ui.report_summary_table import ReportSummaryTableController


class ReportSummaryTableControllerTest(unittest.TestCase):
    def test_populate_table_uses_injected_color_swatch_factory(self):
        swatch = object()
        factory = MagicMock(return_value=swatch)
        table = MagicMock()
        owner = SimpleNamespace(summary_label=QLabel(""), table=table)
        controller = ReportSummaryTableController(
            owner,
            color_swatch_factory=factory,
        )
        summary = ReportSummary(
            rows=[
                GameReportRow(
                    game_title="Game",
                    total_seconds=120,
                    session_count=1,
                    last_played=datetime(2026, 5, 3, 12, 0),
                )
            ],
            total_seconds=120,
            session_count=1,
        )

        controller.populate_table(summary)

        factory.assert_called_once_with("Game")
        table.setCellWidget.assert_called_once_with(0, 0, swatch)


if __name__ == "__main__":
    unittest.main()
