import unittest

from src.app.display_state import WindowDisplayState
from src.core.window_state import MODE_DEFAULT_SIZES


class WindowDisplayStateTest(unittest.TestCase):
    def test_create_initializes_display_and_tray_state(self):
        state = WindowDisplayState.create(
            display_mode="mid",
            mode_sizes={"mid": [320, 220]},
            startup_window_visible=True,
            tray_overlay_enabled=True,
            overlay_position=[10, 20],
        )

        self.assertEqual(state.display_mode, "mid")
        self.assertEqual(state.mode_sizes, {"mid": (320, 220)})
        self.assertTrue(state.startup_window_visible)
        self.assertTrue(state.tray_overlay_enabled)
        self.assertEqual(state.overlay_position, (10, 20))

    def test_create_copies_default_mode_sizes(self):
        state = WindowDisplayState.create()

        self.assertEqual(state.mode_sizes, MODE_DEFAULT_SIZES)
        self.assertIsNot(state.mode_sizes, MODE_DEFAULT_SIZES)

    def test_create_copies_custom_mode_sizes(self):
        mode_sizes = {"min": [300, 90]}

        state = WindowDisplayState.create(mode_sizes=mode_sizes)
        mode_sizes["min"][0] = 999

        self.assertEqual(state.mode_sizes["min"], (300, 90))


if __name__ == "__main__":
    unittest.main()
