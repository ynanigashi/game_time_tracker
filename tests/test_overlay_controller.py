import unittest
from types import SimpleNamespace

from tests.test_stubs import install_stubs

install_stubs()

from src.app.controllers.overlay import MainWindowOverlayController


class MainWindowOverlayControllerTest(unittest.TestCase):
    def test_refresh_overlay_time_uses_injected_widget_providers(self):
        calls = []
        overlay = SimpleNamespace(set_today_text=lambda text: calls.append(text))
        today_display = SimpleNamespace(text=lambda: "00:10:00")
        controller = MainWindowOverlayController(
            SimpleNamespace(),
            overlay_window_provider=lambda: overlay,
            today_time_display_provider=lambda: today_display,
        )

        controller.refresh_overlay_time()

        self.assertEqual(calls, ["00:10:00"])

    def test_close_overlay_uses_injected_setter(self):
        calls = []
        overlay = SimpleNamespace(close=lambda: calls.append("close"))
        controller = MainWindowOverlayController(
            SimpleNamespace(),
            overlay_window_provider=lambda: overlay,
            set_overlay_window=lambda window: calls.append(("set", window)),
        )

        controller.close_overlay()

        self.assertEqual(calls, ["close", ("set", None)])

    def test_save_overlay_position_uses_injected_save_callback(self):
        calls = []
        controller = MainWindowOverlayController(
            SimpleNamespace(),
            save_window_state=lambda: calls.append("save"),
        )

        controller._save_overlay_position()

        self.assertEqual(calls, ["save"])

    def test_visibility_uses_injected_playing_and_cover_callbacks(self):
        controller = MainWindowOverlayController(
            SimpleNamespace(isVisible=lambda: True, isActiveWindow=lambda: False),
            has_playing_games=lambda: True,
            today_display_cover_state=lambda: (True, "covered"),
        )

        self.assertEqual(controller._evaluate_overlay_visibility(), (True, "covered"))

    def test_visibility_hides_when_injected_playing_callback_is_false(self):
        controller = MainWindowOverlayController(
            SimpleNamespace(isVisible=lambda: True),
            has_playing_games=lambda: False,
            today_display_cover_state=lambda: (True, "covered"),
        )

        self.assertEqual(
            controller._evaluate_overlay_visibility(),
            (False, "no_playing_game"),
        )


if __name__ == "__main__":
    unittest.main()
