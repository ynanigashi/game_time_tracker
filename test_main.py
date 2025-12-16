import sys
import types
import unittest
from datetime import datetime, timedelta

# Provide lightweight stubs before importing main to avoid real dependencies.
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


class TestMainLogic(unittest.TestCase):
    def test_is_game_detected_non_browser_excludes_browser(self):
        game = main.GameEntry(
            game_title="Test Game",
            window_title="Test Game",
            play_with_friends=False,
            is_browser_game=False,
        )
        window_titles = ["Test Game - Google Chrome"]
        self.assertFalse(main.is_game_detected(game, window_titles))

    def test_is_game_detected_browser_game_allows_browser(self):
        game = main.GameEntry(
            game_title="Browser Game",
            window_title="Browser Game",
            play_with_friends=False,
            is_browser_game=True,
        )
        window_titles = ["Browser Game - Microsoft Edge"]
        self.assertTrue(main.is_game_detected(game, window_titles))

    def test_finalize_game_session_records_when_over_threshold(self):
        game = main.GameEntry(
            game_title="Long Play",
            window_title="Long Play",
            play_with_friends=True,
            is_browser_game=False,
            is_playing=True,
            start_time=datetime.now() - timedelta(minutes=6),
        )
        handler = FakeLogHandler()

        main.finalize_game_session(game, handler)

        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)
        self.assertEqual(len(handler.records), 1)
        # index, start, end, title, play_with_friends
        self.assertEqual(handler.records[0][0], 1)
        self.assertEqual(handler.records[0][3], "Long Play")
        self.assertTrue(handler.records[0][4])

    def test_finalize_game_session_skips_under_threshold(self):
        game = main.GameEntry(
            game_title="Short Play",
            window_title="Short Play",
            play_with_friends=False,
            is_browser_game=False,
            is_playing=True,
            start_time=datetime.now() - timedelta(minutes=3),
        )
        handler = FakeLogHandler()

        main.finalize_game_session(game, handler)

        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)
        self.assertEqual(handler.records, [])


if __name__ == "__main__":
    unittest.main()
