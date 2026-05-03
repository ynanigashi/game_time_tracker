import unittest
from types import SimpleNamespace

from tests.test_stubs import FakeAction, install_stubs

install_stubs()

from src.app.controllers.tray import MainWindowTrayController
from src.app.tray_state import TrayActionState


class MainWindowTrayControllerTest(unittest.TestCase):
    def test_sync_window_actions_uses_injected_action_state(self):
        action_state = TrayActionState(
            show_action=FakeAction("show"),
            hide_action=FakeAction("hide"),
        )
        owner = SimpleNamespace(isVisible=lambda: False)
        controller = MainWindowTrayController(
            owner,
            base_title="Game Time Tracker",
            action_state=action_state,
        )

        controller.sync_tray_window_actions()

        self.assertTrue(action_state.show_action.visible)
        self.assertFalse(action_state.hide_action.visible)


if __name__ == "__main__":
    unittest.main()
