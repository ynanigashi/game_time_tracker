import unittest

from src.app.lifecycle_state import AppLifecycleState


class AppLifecycleStateTest(unittest.TestCase):
    def test_defaults_to_running_without_startup_override(self):
        state = AppLifecycleState()

        self.assertFalse(state.is_quitting)
        self.assertFalse(state.force_startup_window_visible)

    def test_flags_are_mutable(self):
        state = AppLifecycleState()

        state.is_quitting = True
        state.force_startup_window_visible = True

        self.assertTrue(state.is_quitting)
        self.assertTrue(state.force_startup_window_visible)


if __name__ == "__main__":
    unittest.main()
