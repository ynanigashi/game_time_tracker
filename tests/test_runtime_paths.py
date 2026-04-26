import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.infra import runtime_paths


class TestRuntimePaths(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolve_config_file_migrates_legacy_file(self):
        legacy_path = self.base_dir / "config.ini"
        legacy_path.write_text("[LOGHANDLER]\n", encoding="utf-8")

        with patch("src.infra.runtime_paths.app_base_dir", return_value=self.base_dir):
            resolved = runtime_paths.resolve_config_file()

        self.assertEqual(resolved, self.base_dir / "config" / "config.ini")
        self.assertTrue(resolved.exists())
        self.assertFalse(legacy_path.exists())

    def test_resolve_config_file_prefers_current_file(self):
        legacy_path = self.base_dir / "config.ini"
        current_path = self.base_dir / "config" / "config.ini"
        legacy_path.write_text("legacy", encoding="utf-8")
        current_path.parent.mkdir(parents=True)
        current_path.write_text("current", encoding="utf-8")

        with patch("src.infra.runtime_paths.app_base_dir", return_value=self.base_dir):
            resolved = runtime_paths.resolve_config_file()

        self.assertEqual(resolved, current_path)
        self.assertEqual(current_path.read_text(encoding="utf-8"), "current")
        self.assertTrue(legacy_path.exists())

    def test_resolve_log_file_migrates_legacy_file(self):
        legacy_path = self.base_dir / "game_time_tracker.log"
        legacy_path.write_text("legacy log", encoding="utf-8")

        with patch("src.infra.runtime_paths.app_base_dir", return_value=self.base_dir):
            resolved = runtime_paths.resolve_log_file()

        self.assertEqual(resolved, self.base_dir / "logs" / "game_time_tracker.log")
        self.assertTrue(resolved.exists())
        self.assertFalse(legacy_path.exists())

    def test_resolve_window_state_file_migrates_legacy_file(self):
        legacy_path = self.base_dir / "window_state.txt"
        legacy_path.write_text("{}", encoding="utf-8")

        with patch("src.infra.runtime_paths.app_base_dir", return_value=self.base_dir):
            resolved = runtime_paths.resolve_window_state_file()

        self.assertEqual(resolved, self.base_dir / "data" / "window_state.txt")
        self.assertTrue(resolved.exists())
        self.assertFalse(legacy_path.exists())


if __name__ == "__main__":
    unittest.main()
