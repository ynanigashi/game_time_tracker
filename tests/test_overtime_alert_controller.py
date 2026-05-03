import unittest
from types import SimpleNamespace

from tests.test_stubs import install_stubs

install_stubs()

from src.app.alert_state import GameAlertState
from src.app.controllers.overtime_alert import MainWindowOvertimeAlertController


class MainWindowOvertimeAlertControllerTest(unittest.TestCase):
    def test_enabled_and_tracker_use_injected_state(self):
        owner = SimpleNamespace()
        state = GameAlertState.create(enabled=False, thresholds_minutes=(45,))
        controller = MainWindowOvertimeAlertController(owner, state)

        self.assertFalse(controller.is_enabled())
        controller.set_enabled(True)

        self.assertTrue(state.overtime_alert_enabled)
        self.assertIs(controller.get_tracker(), state.overtime_alert_tracker)


if __name__ == "__main__":
    unittest.main()
