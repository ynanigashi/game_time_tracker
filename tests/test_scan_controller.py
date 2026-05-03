import unittest
from types import SimpleNamespace

from src.app.controllers.scan import MainWindowScanController
from src.core.domain import ScanResult


class MainWindowScanControllerTest(unittest.TestCase):
    def _create_controller(self, owner, calls, **overrides):
        defaults = {
            "games_provider": lambda: [],
            "scan_result_updater": lambda active, inactive, titles: calls.append(
                ("state", active, inactive, titles)
            ),
            "update_active_list": lambda active, inactive: calls.append(
                ("active", active, inactive)
            ),
            "update_window_list": lambda titles: calls.append(("windows", titles)),
            "update_scan_status": lambda active, inactive: calls.append(
                ("status_update", active, inactive)
            ),
            "set_status": lambda message: calls.append(("status", message)),
            "load_today_game_minutes": lambda: {"Game": 12.0},
            "get_today_stats": lambda: ({"Game": 12.0}, 720.0),
        }
        defaults.update(overrides)
        return MainWindowScanController(owner, **defaults)

    def test_apply_scan_result_uses_injected_callbacks(self):
        calls = []
        controller = self._create_controller(SimpleNamespace(), calls)
        active = [SimpleNamespace(title="Active")]
        inactive = [SimpleNamespace(title="Inactive")]

        controller.apply_scan_result(
            ["Window"],
            ScanResult(
                active_games=active,
                inactive_games=inactive,
                recorded_seconds=0.0,
            ),
        )

        self.assertEqual(
            calls,
            [
                ("state", active, inactive, ["Window"]),
                ("active", active, inactive),
                ("windows", ["Window"]),
                ("status_update", active, inactive),
            ],
        )

    def test_load_today_stats_use_injected_stats_callback(self):
        controller = self._create_controller(SimpleNamespace(), [])

        self.assertEqual(controller.load_today_game_minutes(), {"Game": 12.0})
        self.assertEqual(controller.load_today_completed_seconds(), 720.0)


if __name__ == "__main__":
    unittest.main()
