import configparser
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.infra.settings_store import SettingsStore


class TestSettingsStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "data" / "settings.sqlite3"
        self.store = SettingsStore(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_config_roundtrip(self):
        config = configparser.ConfigParser()
        config["LOGHANDLER"] = {
            "json_file_path": "service_account.json",
            "sheet_key": "log_key",
        }
        config["GAMEINFO"] = {
            "sheet_key": "game_key",
            "sheet_gid": "123",
        }

        self.store.save_config(config)
        loaded = self.store.load_config()

        self.assertEqual(
            loaded["LOGHANDLER"]["json_file_path"],
            "service_account.json",
        )
        self.assertEqual(loaded["GAMEINFO"]["sheet_gid"], "123")

    def test_window_state_roundtrip(self):
        state = {
            "x": 10,
            "y": 20,
            "display_mode": "mid",
            "mode_sizes": {"mid": [300, 200]},
            "overtime_alert_enabled": False,
        }

        self.store.save_window_state(state)

        self.assertEqual(self.store.load_window_state(), state)

    def test_migrate_window_state_file_imports_and_removes_file(self):
        state_file = Path(self.temp_dir.name) / "data" / "window_state.txt"
        state_file.parent.mkdir(parents=True)
        state_file.write_text(
            json.dumps({"x": 10, "y": 20, "display_mode": "mid"}),
            encoding="utf-8",
        )

        self.store.migrate_window_state_file(state_file)

        loaded = self.store.load_window_state()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["x"], 10)
        self.assertFalse(state_file.exists())

    def test_schema_version_is_recorded(self):
        self.store.load_config()

        conn = sqlite3.connect(self.store.db_path)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(version, SettingsStore.SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
