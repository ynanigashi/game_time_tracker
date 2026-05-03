import unittest
from types import SimpleNamespace

from src.core.reporting import ReportSummary
from src.ui.report_graph_unit import ReportGraphUnitController
from src.ui.report_graph_unit_state import ReportGraphUnitState
from src.ui.report_tab_state import ReportTabState


class ReportGraphUnitControllerTest(unittest.TestCase):
    def test_set_graph_unit_reuses_injected_summary_cache(self):
        calls = {
            "populate_chart": 0,
            "summary_refresh": 0,
            "dirty": [],
            "clean": [],
        }
        owner = SimpleNamespace()
        tab_state = ReportTabState(
            last_summary=ReportSummary(rows=[], total_seconds=0, session_count=0)
        )
        controller = ReportGraphUnitController(
            owner,
            ReportGraphUnitState(),
            tab_state,
            summary_tab=0,
            trend_tab=1,
            unit_toggle_style="",
            set_debug_message=lambda *_args, **_kwargs: None,
            current_tab_index=lambda: 0,
            refresh_summary=lambda: calls.__setitem__(
                "summary_refresh",
                calls["summary_refresh"] + 1,
            ),
            populate_chart=lambda _summary: calls.__setitem__(
                "populate_chart",
                calls["populate_chart"] + 1,
            ),
            refresh_trend_tab=lambda: None,
            populate_trend_chart=lambda _series: None,
            mark_tab_clean=lambda tab: calls["clean"].append(tab),
            mark_tab_dirty=lambda tab: calls["dirty"].append(tab),
        )

        controller.set_graph_unit(True)

        self.assertEqual(calls["summary_refresh"], 0)
        self.assertEqual(calls["populate_chart"], 1)
        self.assertEqual(calls["clean"], [0])
        self.assertEqual(calls["dirty"], [1])


if __name__ == "__main__":
    unittest.main()
