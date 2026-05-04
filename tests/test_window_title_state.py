import unittest

from src.app.window_title_state import WindowTitleState


class WindowTitleStateTest(unittest.TestCase):
    def test_defaults_to_disconnected(self):
        state = WindowTitleState()

        self.assertFalse(state.copy_connected)
        self.assertFalse(state.context_menu_connected)

    def test_connection_flags_are_mutable(self):
        state = WindowTitleState()

        state.copy_connected = True
        state.context_menu_connected = True

        self.assertTrue(state.copy_connected)
        self.assertTrue(state.context_menu_connected)


if __name__ == "__main__":
    unittest.main()
