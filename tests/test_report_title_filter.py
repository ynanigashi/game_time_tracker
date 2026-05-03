import unittest
from types import SimpleNamespace

from tests.test_stubs import install_stubs

install_stubs()

from src.core.reporting import ReportSummary
from src.ui.report_tab_state import ReportTabState
from src.ui.report_title_filter import ReportTitleFilterController
from src.ui.report_title_filter_state import ReportTitleFilterState


class ReportTitleFilterControllerTest(unittest.TestCase):
    def test_load_summary_uses_injected_tab_state_cache(self):
        cached_summary = ReportSummary(rows=[], total_seconds=0, session_count=0)
        tab_state = ReportTabState(
            title_filter_dirty=False,
            title_filter_summary=cached_summary,
        )
        owner = SimpleNamespace(log_handler=SimpleNamespace())
        controller = ReportTitleFilterController(
            owner,
            ReportTitleFilterState(),
            tab_state,
        )

        self.assertIs(controller.load_title_filter_summary(), cached_summary)

    def test_load_summary_stores_result_in_injected_tab_state(self):
        summary = ReportSummary(rows=[], total_seconds=0, session_count=0)
        calls = {"count": 0}

        def get_report_stats(**_kwargs):
            calls["count"] += 1
            return summary

        tab_state = ReportTabState(title_filter_dirty=True)
        owner = SimpleNamespace(
            log_handler=SimpleNamespace(get_report_stats=get_report_stats)
        )
        controller = ReportTitleFilterController(
            owner,
            ReportTitleFilterState(),
            tab_state,
        )

        self.assertIs(controller.load_title_filter_summary(), summary)
        self.assertIs(tab_state.title_filter_summary, summary)
        self.assertEqual(calls["count"], 1)


if __name__ == "__main__":
    unittest.main()
