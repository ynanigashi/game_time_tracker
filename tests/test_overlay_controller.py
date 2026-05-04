import unittest
from types import SimpleNamespace

from tests.test_stubs import install_stubs

install_stubs()

from src.app.controllers.overlay import MainWindowOverlayController


class MainWindowOverlayControllerTest(unittest.TestCase):
    def _create_controller(self, **overrides):
        defaults = {
            "overlay_window_provider": lambda: None,
            "set_overlay_window": lambda _window: None,
            "set_overlay_position": lambda _position: None,
            "get_overlay_position": lambda: None,
            "today_time_display_provider": lambda: None,
            "save_window_state": lambda: None,
            "has_playing_games": lambda: False,
            "today_display_cover_state": None,
            "is_own_window": None,
            "is_main_window_visible": lambda: False,
            "is_main_window_active": lambda: False,
            "is_active_window_own": lambda _active_window: False,
            "window_geometry": lambda: None,
            "move_window": lambda _x, _y: None,
            "get_tray_overlay_enabled": lambda: False,
        }
        defaults.update(overrides)
        return MainWindowOverlayController(**defaults)

    def test_refresh_overlay_time_uses_injected_widget_providers(self):
        calls = []
        overlay = SimpleNamespace(set_today_text=lambda text: calls.append(text))
        today_display = SimpleNamespace(text=lambda: "00:10:00")
        controller = self._create_controller(
            overlay_window_provider=lambda: overlay,
            today_time_display_provider=lambda: today_display,
        )

        controller.refresh_overlay_time()

        self.assertEqual(calls, ["00:10:00"])

    def test_close_overlay_uses_injected_setter(self):
        calls = []
        overlay = SimpleNamespace(close=lambda: calls.append("close"))
        controller = self._create_controller(
            overlay_window_provider=lambda: overlay,
            set_overlay_window=lambda window: calls.append(("set", window)),
        )

        controller.close_overlay()

        self.assertEqual(calls, ["close", ("set", None)])

    def test_save_overlay_position_uses_injected_save_callback(self):
        calls = []
        controller = self._create_controller(
            save_window_state=lambda: calls.append("save"),
        )

        controller._save_overlay_position()

        self.assertEqual(calls, ["save"])

    def test_visibility_uses_injected_playing_and_cover_callbacks(self):
        controller = self._create_controller(
            is_main_window_visible=lambda: True,
            is_main_window_active=lambda: False,
            has_playing_games=lambda: True,
            today_display_cover_state=lambda: (True, "covered"),
        )

        self.assertEqual(controller._evaluate_overlay_visibility(), (True, "covered"))

    def test_visibility_hides_when_injected_playing_callback_is_false(self):
        controller = self._create_controller(
            is_main_window_visible=lambda: True,
            has_playing_games=lambda: False,
            today_display_cover_state=lambda: (True, "covered"),
        )

        self.assertEqual(
            controller._evaluate_overlay_visibility(),
            (False, "no_playing_game"),
        )

    def test_overlay_moved_uses_injected_position_setter(self):
        calls = []
        controller = self._create_controller(
            set_overlay_position=lambda position: calls.append(position),
        )

        controller._on_overlay_moved(12, 34)

        self.assertEqual(calls, [(12, 34)])


if __name__ == "__main__":
    unittest.main()
