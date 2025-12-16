import sys
import types
import unittest
from datetime import datetime, timedelta

# Stub external dependencies before importing the app.
fake_gspread = types.SimpleNamespace(
    service_account=lambda filename=None: None,
    exceptions=types.SimpleNamespace(APIError=Exception),
)
fake_pygetwindow = types.SimpleNamespace(getAllWindows=lambda: [])
sys.modules.setdefault("gspread", fake_gspread)
sys.modules.setdefault("pygetwindow", fake_pygetwindow)

import main


class FakeLogHandler:
    def __init__(self):
        self.records = []
        self.current_index = 0

    def format_datetime_to_gss_style(self, dt: datetime) -> str:
        return dt.strftime("%Y/%m/%d %H:%M:%S")

    def get_and_increment_index(self) -> int:
        self.current_index += 1
        return self.current_index

    def save_record(self, values):
        self.records.append(values)


class TestGameEntry(unittest.TestCase):
    def test_matches_window_browser_game_allows_browser_titles(self):
        game = main.GameEntry(game_title="BrowserGame", window_title="BrowserGame", is_browser_game=True)
        self.assertTrue(game.matches_window("BrowserGame - Chrome", browsers=["Chrome"]))

    def test_matches_window_normal_game_excludes_browsers(self):
        game = main.GameEntry(game_title="NormalGame", window_title="NormalGame", is_browser_game=False)
        self.assertFalse(game.matches_window("NormalGame - Chrome", browsers=["Chrome"]))


class TestSessionRecorder(unittest.TestCase):
    def test_record_over_threshold_appends(self):
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="LongPlay", window_title="LongPlay", play_with_friends=True, is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=6)

        recorder.record(game)

        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)
        self.assertEqual(len(handler.records), 1)
        self.assertEqual(handler.records[0][0], 1)
        self.assertEqual(handler.records[0][3], "LongPlay")
        self.assertTrue(handler.records[0][4])

    def test_record_under_threshold_skips(self):
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="ShortPlay", window_title="ShortPlay", play_with_friends=False, is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=2)

        recorder.record(game)

        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)
        self.assertEqual(handler.records, [])


class TestUtils(unittest.TestCase):
    def test_format_elapsed(self):
        start = datetime.now() - timedelta(minutes=1, seconds=5)
        elapsed_str = main._format_elapsed(start)
        self.assertTrue(elapsed_str.startswith("1分"))
        self.assertIn("秒", elapsed_str)


if __name__ == "__main__":
    unittest.main()
