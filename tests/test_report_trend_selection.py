import unittest
from datetime import date
from types import SimpleNamespace

from tests.test_stubs import install_stubs

install_stubs()

from src.core.reporting import TrendPoint, TrendSeries
from src.ui.report_tab_state import ReportTabState
from src.ui.report_trend_selection import ReportTrendSelectionController
from src.ui.report_trend_selection_state import ReportTrendSelectionState


class ReportTrendSelectionControllerTest(unittest.TestCase):
    def _series(self):
        return [
            TrendSeries(
                title="Game",
                points=[
                    TrendPoint("Jan", date(2026, 1, 1), date(2026, 1, 31), 60),
                    TrendPoint("Feb", date(2026, 2, 1), date(2026, 2, 28), 120),
                ],
            )
        ]

    def test_clear_selection_uses_injected_tab_state_series(self):
        calls = {"rows": None}
        owner = SimpleNamespace(
            trend_chart_view=None,
            clear_trend_selection_button=SimpleNamespace(setEnabled=lambda _value: None),
            trend_summary_label=SimpleNamespace(setText=lambda _text: None),
            trend_table=SimpleNamespace(
                setRowCount=lambda rows: calls.__setitem__("rows", rows),
                setItem=lambda *_args: None,
            ),
            _trend_series_label=lambda: "系列",
            _set_debug_message=lambda *_args, **_kwargs: None,
        )
        tab_state = ReportTabState(last_trend_series=self._series())
        state = ReportTrendSelectionState(selected_indices=(0, 1))
        controller = ReportTrendSelectionController(owner, state, tab_state)

        controller.clear_trend_selection()

        self.assertIsNone(state.selected_indices)
        self.assertEqual(calls["rows"], 2)


if __name__ == "__main__":
    unittest.main()
