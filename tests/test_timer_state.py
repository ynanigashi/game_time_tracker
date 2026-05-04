import unittest

from src.app.timer_state import TimerState


class TimerStateTest(unittest.TestCase):
    def test_defaults_to_no_timers(self):
        state = TimerState()

        self.assertIsNone(state.scan_timer)
        self.assertIsNone(state.ui_timer)

    def test_timer_references_are_assignable(self):
        state = TimerState()
        scan_timer = object()
        ui_timer = object()

        state.scan_timer = scan_timer
        state.ui_timer = ui_timer

        self.assertIs(state.scan_timer, scan_timer)
        self.assertIs(state.ui_timer, ui_timer)


if __name__ == "__main__":
    unittest.main()
