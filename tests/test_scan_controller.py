import unittest
from types import SimpleNamespace

from src.app.controllers.scan import MainWindowScanController
from src.core.domain import ScanResult


class MainWindowScanControllerTest(unittest.TestCase):
    def _create_controller(self, calls, **overrides):
        defaults = {
            "state_tracker": SimpleNamespace(
                scan=lambda **_kwargs: ScanResult(
                    active_games=[],
                    inactive_games=[],
                    recorded_seconds=0.0,
                )
            ),
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
        return MainWindowScanController(**defaults)

    def test_apply_scan_result_uses_injected_callbacks(self):
        calls = []
        controller = self._create_controller(calls)
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
        controller = self._create_controller([])

        self.assertEqual(controller.load_today_game_minutes(), {"Game": 12.0})
        self.assertEqual(controller.load_today_completed_seconds(), 720.0)

    def test_scan_games_uses_injected_state_tracker(self):
        calls = []

        def scan(**kwargs):
            calls.append(kwargs)
            return ScanResult(
                active_games=["active"],
                inactive_games=["inactive"],
                recorded_seconds=0.0,
            )

        controller = self._create_controller(
            calls,
            state_tracker=SimpleNamespace(scan=scan),
            games_provider=lambda: ["game"],
        )

        result = controller.scan_games(["Window"], "Foreground")

        self.assertEqual(result.active_games, ["active"])
        self.assertEqual(
            calls[0],
            {
                "games": ["game"],
                "window_titles": ["Window"],
                "foreground_title": "Foreground",
                "load_today_game_minutes_callback": controller.load_today_game_minutes_callback,
            },
        )


if __name__ == "__main__":
    unittest.main()
