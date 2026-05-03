import unittest
from unittest.mock import MagicMock

from tests.test_stubs import install_stubs

install_stubs()

from src.ui.report_log_operation_state import ReportLogOperationState


class ReportLogOperationStateTest(unittest.TestCase):
    def test_defaults_to_idle_operation_state(self):
        state = ReportLogOperationState()

        try:
            self.assertIsNone(state.future)
            self.assertIsNone(state.timer)
            self.assertIsNone(state.finish_callback)
        finally:
            state.shutdown()

    def test_shutdown_stops_timer_and_clears_callback(self):
        state = ReportLogOperationState()
        timer = MagicMock()
        state.timer = timer
        state.finish_callback = lambda result: None

        state.shutdown()

        timer.stop.assert_called_once()
        self.assertIsNone(state.timer)
        self.assertIsNone(state.finish_callback)


if __name__ == "__main__":
    unittest.main()
