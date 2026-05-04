import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from tests.test_stubs import install_stubs
install_stubs()

from src.app.controllers import MainWindowStateController
from src.infra.settings_store import SettingsStore


class TestMainWindowStateController(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.state_file = self.base_dir / "data" / "window_state.txt"
        self.store = SettingsStore(self.base_dir / "data" / "settings.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_all_migrates_legacy_file_to_sqlite(self):
        self.state_file.parent.mkdir(parents=True)
        self.state_file.write_text(
            json.dumps({
                "x": 10,
                "y": 20,
                "display_mode": "mid",
                "mode_sizes": {"mid": [300, 200]},
                "overtime_alert_enabled": False,
            }),
            encoding="utf-8",
        )

        controller = MainWindowStateController(self.state_file, self.store)
        x, y, mode, mode_sizes, overtime_alert_enabled = controller.load_all()

        self.assertEqual((x, y, mode), (10, 20, "mid"))
        self.assertEqual(mode_sizes["mid"], (300, 200))
        self.assertFalse(overtime_alert_enabled)
        self.assertFalse(self.state_file.exists())

    def test_save_persists_to_sqlite(self):
        controller = MainWindowStateController(self.state_file, self.store)
        geom = MagicMock()
        geom.x.return_value = 10
        geom.y.return_value = 20
        geom.width.return_value = 350
        geom.height.return_value = 250
        mode_sizes = {"max": (480, 400), "mid": (300, 200), "min": (320, 180)}

        controller.save(geom, "mid", mode_sizes, overtime_alert_enabled=False)
        loaded = self.store.load_window_state()

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["x"], 10)
        self.assertEqual(loaded["mode_sizes"]["mid"], [350, 250])
        self.assertFalse(loaded["overtime_alert_enabled"])


if __name__ == "__main__":
    unittest.main()
