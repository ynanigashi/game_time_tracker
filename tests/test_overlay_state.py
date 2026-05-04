import unittest

from src.app.overlay_state import OverlayVisibilityLogState


class OverlayVisibilityLogStateTest(unittest.TestCase):
    def test_defaults_to_no_logged_visibility(self):
        state = OverlayVisibilityLogState()

        self.assertIsNone(state.last_should_show)
        self.assertIsNone(state.last_reason)
        self.assertEqual(state.last_log_monotonic, 0.0)

    def test_logged_visibility_fields_are_mutable(self):
        state = OverlayVisibilityLogState()

        state.last_should_show = True
        state.last_reason = "covered"
        state.last_log_monotonic = 12.5

        self.assertTrue(state.last_should_show)
        self.assertEqual(state.last_reason, "covered")
        self.assertEqual(state.last_log_monotonic, 12.5)


if __name__ == "__main__":
    unittest.main()
