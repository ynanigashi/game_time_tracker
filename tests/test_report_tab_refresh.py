import unittest
from types import SimpleNamespace

from src.ui.report_tab_refresh import ReportTabRefreshController
from src.ui.report_tab_state import ReportTabState


class ReportTabRefreshControllerTest(unittest.TestCase):
    def _controller(self, current_index=0):
        owner = SimpleNamespace(
            tabs=SimpleNamespace(currentIndex=lambda: current_index),
            summary_calls=0,
            trend_calls=0,
            log_calls=0,
        )
        owner.refresh_summary = lambda: setattr(
            owner,
            "summary_calls",
            owner.summary_calls + 1,
        )
        owner.refresh_trend_tab = lambda: setattr(
            owner,
            "trend_calls",
            owner.trend_calls + 1,
        )
        owner.refresh_logs = lambda: setattr(owner, "log_calls", owner.log_calls + 1)
        state = ReportTabState()
        controller = ReportTabRefreshController(
            owner,
            state,
            summary_tab=0,
            trend_tab=1,
            log_tab=2,
        )
        return controller, state, owner

    def test_refresh_uses_injected_state_and_current_tab(self):
        controller, state, owner = self._controller(current_index=1)

        controller.refresh()

        self.assertEqual(owner.trend_calls, 1)
        self.assertIn(0, state.dirty_tabs)
        self.assertNotIn(1, state.dirty_tabs)
        self.assertIn(2, state.dirty_tabs)
        self.assertIn(1, state.loaded_tabs)

    def test_clean_loaded_tab_does_not_refresh_without_force(self):
        controller, state, owner = self._controller(current_index=2)
        state.loaded_tabs.add(2)

        controller.refresh_current_tab(force=False)

        self.assertEqual(owner.log_calls, 0)


if __name__ == "__main__":
    unittest.main()
