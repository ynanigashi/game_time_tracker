import unittest

from src.app.tray_state import TrayActionState


class TrayActionStateTest(unittest.TestCase):
    def test_defaults_to_no_actions(self):
        state = TrayActionState()

        self.assertIsNone(state.show_action)
        self.assertIsNone(state.hide_action)
        self.assertIsNone(state.startup_show_action)
        self.assertIsNone(state.startup_hide_action)
        self.assertIsNone(state.overlay_action)

    def test_action_references_are_assignable(self):
        state = TrayActionState()
        show_action = object()
        hide_action = object()

        state.show_action = show_action
        state.hide_action = hide_action

        self.assertIs(state.show_action, show_action)
        self.assertIs(state.hide_action, hide_action)


if __name__ == "__main__":
    unittest.main()
