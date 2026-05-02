import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from tests.test_stubs import install_stubs

install_stubs()

from src.core.models import GameEntry
from src.ui.manual_record_dialog import ELAPSED_TIMER_INTERVAL_MS, ManualRecordDialog


class TestManualRecordDialog(unittest.TestCase):
    def test_parse_datetime_accepts_seconds(self):
        result = ManualRecordDialog.parse_datetime("2026/05/01 21:30:45")

        self.assertEqual(result, datetime(2026, 5, 1, 21, 30, 45))

    def test_parse_datetime_accepts_minutes(self):
        result = ManualRecordDialog.parse_datetime("2026/05/01 21:30")

        self.assertEqual(result, datetime(2026, 5, 1, 21, 30, 0))

    def test_timer_updates_at_10_fps(self):
        dialog = ManualRecordDialog(on_save=lambda record: True)

        self.assertEqual(dialog._elapsed_timer.interval, ELAPSED_TIMER_INTERVAL_MS)

    def test_collect_record_builds_game_entry(self):
        dialog = ManualRecordDialog.__new__(ManualRecordDialog)
        game = GameEntry(
            game_id="game-1",
            game_title="NTE",
            window_title="NTE Window",
            is_browser_game=True,
        )
        dialog._selected_game = MagicMock(return_value=game)
        dialog.start_time_edit = MagicMock()
        dialog.start_time_edit.text.return_value = "2026/05/01 21:00"
        dialog.end_time_edit = MagicMock()
        dialog.end_time_edit.text.return_value = "2026/05/01 22:00"

        record = dialog._collect_record()

        self.assertEqual(record.game.game_title, "NTE")
        self.assertEqual(record.game.window_title, "NTE Window")
        self.assertEqual(record.game.game_id, "game-1")
        self.assertTrue(record.game.is_browser_game)
        self.assertFalse(record.game.play_with_friends)
        self.assertEqual(record.start_time, datetime(2026, 5, 1, 21, 0, 0))
        self.assertEqual(record.end_time, datetime(2026, 5, 1, 22, 0, 0))

    def test_collect_record_rejects_end_before_start(self):
        dialog = ManualRecordDialog.__new__(ManualRecordDialog)
        dialog._selected_game = MagicMock(
            return_value=GameEntry(game_title="NTE", window_title="NTE")
        )
        dialog.start_time_edit = MagicMock()
        dialog.start_time_edit.text.return_value = "2026/05/01 22:00"
        dialog.end_time_edit = MagicMock()
        dialog.end_time_edit.text.return_value = "2026/05/01 21:00"

        with self.assertRaises(ValueError):
            dialog._collect_record()

    def test_set_games_populates_dropdown(self):
        dialog = ManualRecordDialog.__new__(ManualRecordDialog)
        dialog.game_combo = MagicMock()
        selected = GameEntry(
            game_title="NTE",
            window_title="NTE",
            play_with_friends=True,
        )

        dialog.set_games([selected])

        dialog.game_combo.clear.assert_called_once()
        dialog.game_combo.addItem.assert_called_once_with("NTE", selected)

    def test_start_and_stop_timer_fill_times_and_elapsed(self):
        start = datetime(2026, 5, 1, 21, 0, 0)
        stop = start + timedelta(minutes=12, seconds=34)
        now_values = [start, stop]
        dialog = ManualRecordDialog.__new__(ManualRecordDialog)
        dialog._now_provider = lambda: now_values.pop(0)
        dialog._timer_started_at = None
        dialog.start_time_edit = MagicMock()
        dialog.end_time_edit = MagicMock()
        dialog.elapsed_display = MagicMock()
        dialog.start_button = MagicMock()
        dialog.stop_button = MagicMock()
        dialog._elapsed_timer = MagicMock()

        dialog._start_timer()
        dialog._stop_timer()

        dialog.start_time_edit.setText.assert_called_once_with("2026/05/01 21:00:00")
        dialog.end_time_edit.setText.assert_any_call("")
        dialog.end_time_edit.setText.assert_called_with("2026/05/01 21:12:34")
        dialog.elapsed_display.setText.assert_called_with("00:12:34.0")
        dialog._elapsed_timer.start.assert_called_once()
        dialog._elapsed_timer.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
