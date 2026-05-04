import unittest
from types import SimpleNamespace

from tests.test_stubs import install_stubs

install_stubs()

from src.app.alert_state import GameAlertState
from src.app.controllers.overtime_alert import MainWindowOvertimeAlertController


class MainWindowOvertimeAlertControllerTest(unittest.TestCase):
    def _create_controller(self, owner, state, **overrides):
        defaults = {
            "toggle_provider": lambda: None,
            "on_toggle_changed": lambda _checked: None,
            "active_games_provider": lambda: [],
            "inactive_games_provider": lambda: [],
            "calculate_today_total_seconds": lambda _active, _inactive, _now: 0.0,
            "sync_overlay": lambda: None,
        }
        defaults.update(overrides)
        return MainWindowOvertimeAlertController(owner, state, **defaults)

    def test_enabled_and_tracker_use_injected_state(self):
        owner = SimpleNamespace()
        state = GameAlertState.create(enabled=False, thresholds_minutes=(45,))
        controller = self._create_controller(owner, state)

        self.assertFalse(controller.is_enabled())
        controller.set_enabled(True)

        self.assertTrue(state.overtime_alert_enabled)
        self.assertIs(controller.get_tracker(), state.overtime_alert_tracker)

    def test_on_toggled_uses_injected_total_and_overlay_callbacks(self):
        calls = []
        state = GameAlertState.create(enabled=False, thresholds_minutes=(45,))
        controller = self._create_controller(
            SimpleNamespace(),
            state,
            active_games_provider=lambda: ["active"],
            inactive_games_provider=lambda: ["inactive"],
            calculate_today_total_seconds=lambda active, inactive, _now: calls.append(
                ("total", active, inactive)
            )
            or 1800.0,
            sync_overlay=lambda: calls.append("overlay"),
        )

        controller.on_toggled(True)

        self.assertTrue(state.overtime_alert_enabled)
        self.assertEqual(calls, [("total", ["active"], ["inactive"]), "overlay"])
        self.assertEqual(state.overtime_alert_tracker.last_checked_seconds, 1800.0)


if __name__ == "__main__":
    unittest.main()
