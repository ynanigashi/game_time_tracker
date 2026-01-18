import sys
import types
import unittest
from datetime import datetime, timedelta

# Stub external dependencies before importing the app.
fake_gspread = types.SimpleNamespace(
    service_account=lambda filename=None: None,
    exceptions=types.SimpleNamespace(APIError=Exception),
)
fake_pygetwindow = types.SimpleNamespace(
    getAllWindows=lambda: [],
    getActiveWindow=lambda: None,
)
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

    def get_cached_records(self):
        """キャッシュされたレコードを返す."""
        return self.records

    def save_record(self, values) -> bool:
        """レコードを保存し、キャッシュにも追加。成功時Trueを返す。"""
        if len(values) >= 5:
            self.records.append({
                'index': values[0],
                'start_time': values[1],
                'end_time': values[2],
                'title': values[3],
                'play_with_friends': values[4],
            })
        return True


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
        self.assertEqual(handler.records[0]['index'], 1)
        self.assertEqual(handler.records[0]['title'], "LongPlay")
        self.assertTrue(handler.records[0]['play_with_friends'])

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


class TestSplitByDay(unittest.TestCase):
    """日を跨いだセッション分割のテスト."""

    def setUp(self):
        handler = FakeLogHandler()
        self.recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)

    def test_same_day_no_split(self):
        """同日内のセッションは分割されない."""
        start = datetime(2026, 1, 10, 22, 0, 0)
        end = datetime(2026, 1, 10, 23, 30, 0)
        segments = self.recorder._split_by_day(start, end)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0], (start, end))

    def test_cross_midnight_splits_into_two(self):
        """日を跨ぐセッションは2つに分割される."""
        start = datetime(2026, 1, 10, 23, 30, 0)
        end = datetime(2026, 1, 11, 1, 30, 0)
        segments = self.recorder._split_by_day(start, end)
        self.assertEqual(len(segments), 2)
        # 1日目: 23:30 - 23:59:59.999999
        self.assertEqual(segments[0][0], start)
        self.assertEqual(segments[0][1].date(), datetime(2026, 1, 10).date())
        self.assertEqual(segments[0][1].hour, 23)
        self.assertEqual(segments[0][1].minute, 59)
        # 2日目: 00:00 - 01:30
        self.assertEqual(segments[1][0], datetime(2026, 1, 11, 0, 0, 0))
        self.assertEqual(segments[1][1], end)

    def test_cross_two_days_splits_into_three(self):
        """2日を跨ぐセッションは3つに分割される."""
        start = datetime(2026, 1, 10, 23, 0, 0)
        end = datetime(2026, 1, 12, 2, 0, 0)
        segments = self.recorder._split_by_day(start, end)
        self.assertEqual(len(segments), 3)
        # 1日目
        self.assertEqual(segments[0][0].date(), datetime(2026, 1, 10).date())
        # 2日目
        self.assertEqual(segments[1][0].date(), datetime(2026, 1, 11).date())
        # 3日目
        self.assertEqual(segments[2][0].date(), datetime(2026, 1, 12).date())
        self.assertEqual(segments[2][1], end)

    def test_record_cross_midnight_creates_two_records(self):
        """日を跨ぐプレイで5分以上のセグメントが2つ記録される."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(
            game_title="MidnightGame",
            window_title="MidnightGame",
            is_playing=True,
        )
        # 23:30 - 翌01:30 (各セグメント30分以上)
        game.start_time = datetime(2026, 1, 10, 23, 30, 0)
        # end_session をモック
        original_end_session = game.end_session
        def mock_end_session():
            game.is_playing = False
            start = game.start_time
            game.start_time = None
            return start, datetime(2026, 1, 11, 1, 30, 0)
        game.end_session = mock_end_session

        recorder.record(game)

        self.assertEqual(len(handler.records), 2)
        # 1日目のレコード
        self.assertIn("2026/01/10", handler.records[0]['start_time'])
        # 2日目のレコード
        self.assertIn("2026/01/11", handler.records[1]['start_time'])


class TestLogHandlerCache(unittest.TestCase):
    """LogHandlerのキャッシュ機能テスト."""

    def test_save_record_updates_cache(self):
        """save_record後にget_cached_recordsで新しいレコードが取得できる."""
        handler = FakeLogHandler()
        
        # 初期状態は空
        self.assertEqual(len(handler.get_cached_records()), 0)
        
        # レコードを保存
        handler.save_record([
            1,
            "2026/01/18 10:00:00",
            "2026/01/18 11:00:00",
            "TestGame",
            False,
        ])
        
        # キャッシュに追加されている
        cached = handler.get_cached_records()
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0]['title'], "TestGame")
        self.assertEqual(cached[0]['start_time'], "2026/01/18 10:00:00")
        self.assertEqual(cached[0]['end_time'], "2026/01/18 11:00:00")

    def test_multiple_saves_accumulate_in_cache(self):
        """複数回のsave_recordでキャッシュに蓄積される."""
        handler = FakeLogHandler()
        
        handler.save_record([1, "2026/01/18 10:00:00", "2026/01/18 11:00:00", "Game1", False])
        handler.save_record([2, "2026/01/18 12:00:00", "2026/01/18 13:00:00", "Game2", True])
        handler.save_record([3, "2026/01/18 14:00:00", "2026/01/18 15:00:00", "Game1", False])
        
        cached = handler.get_cached_records()
        self.assertEqual(len(cached), 3)
        self.assertEqual(cached[0]['title'], "Game1")
        self.assertEqual(cached[1]['title'], "Game2")
        self.assertEqual(cached[2]['title'], "Game1")

    def test_cache_can_filter_by_date(self):
        """キャッシュから特定日付のレコードをフィルタできる."""
        handler = FakeLogHandler()
        
        # 異なる日付のレコードを追加
        handler.save_record([1, "2026/01/17 10:00:00", "2026/01/17 11:00:00", "Yesterday", False])
        handler.save_record([2, "2026/01/18 10:00:00", "2026/01/18 11:00:00", "Today1", False])
        handler.save_record([3, "2026/01/18 14:00:00", "2026/01/18 15:00:00", "Today2", False])
        
        # 今日のレコードだけをフィルタ
        today_str = "2026/01/18"
        today_records = [
            r for r in handler.get_cached_records()
            if r['start_time'].startswith(today_str)
        ]
        
        self.assertEqual(len(today_records), 2)
        self.assertEqual(today_records[0]['title'], "Today1")
        self.assertEqual(today_records[1]['title'], "Today2")

    def test_cache_calculates_play_minutes_correctly(self):
        """キャッシュからプレイ時間（分）を正しく計算できる."""
        handler = FakeLogHandler()
        
        # 30分と60分のレコード
        handler.save_record([1, "2026/01/18 10:00:00", "2026/01/18 10:30:00", "Game1", False])
        handler.save_record([2, "2026/01/18 12:00:00", "2026/01/18 13:00:00", "Game2", False])
        handler.save_record([3, "2026/01/18 14:00:00", "2026/01/18 14:45:00", "Game1", False])
        
        # ゲームごとの合計時間を計算
        game_minutes = {}
        for record in handler.get_cached_records():
            start = datetime.strptime(record['start_time'], "%Y/%m/%d %H:%M:%S")
            end = datetime.strptime(record['end_time'], "%Y/%m/%d %H:%M:%S")
            minutes = (end - start).total_seconds() / 60
            title = record['title']
            game_minutes[title] = game_minutes.get(title, 0) + minutes
        
        self.assertEqual(game_minutes['Game1'], 75)  # 30 + 45
        self.assertEqual(game_minutes['Game2'], 60)


class TestGameEntryInactive(unittest.TestCase):
    """GameEntryの非アクティブ機能テスト."""

    def test_initial_state_not_inactive(self):
        """初期状態では非アクティブではない."""
        game = main.GameEntry(game_title="Test", window_title="Test")
        self.assertFalse(game.is_inactive())
        self.assertEqual(game.get_inactive_seconds(), 0.0)

    def test_set_inactive_marks_inactive(self):
        """set_inactive()で非アクティブ状態になる."""
        game = main.GameEntry(game_title="Test", window_title="Test")
        game.set_inactive()
        self.assertTrue(game.is_inactive())
        self.assertIsNotNone(game.inactive_since)

    def test_set_active_clears_inactive(self):
        """set_active()で非アクティブ状態がクリアされる."""
        game = main.GameEntry(game_title="Test", window_title="Test")
        game.set_inactive()
        game.set_active()
        self.assertFalse(game.is_inactive())
        self.assertIsNone(game.inactive_since)

    def test_start_session_clears_inactive(self):
        """start_session()で非アクティブ状態がクリアされる."""
        game = main.GameEntry(game_title="Test", window_title="Test")
        game.inactive_since = datetime.now()
        game.start_session()
        self.assertIsNone(game.inactive_since)

    def test_end_session_clears_inactive(self):
        """end_session()で非アクティブ状態がクリアされる."""
        game = main.GameEntry(game_title="Test", window_title="Test", is_playing=True)
        game.start_time = datetime.now()
        game.inactive_since = datetime.now()
        game.end_session()
        self.assertIsNone(game.inactive_since)

    def test_get_inactive_seconds_returns_elapsed_time(self):
        """get_inactive_seconds()は経過秒数を返す."""
        game = main.GameEntry(game_title="Test", window_title="Test")
        game.inactive_since = datetime.now() - timedelta(seconds=30)
        elapsed = game.get_inactive_seconds()
        self.assertGreaterEqual(elapsed, 29)
        self.assertLess(elapsed, 32)


class TestSessionRecorderWithTimes(unittest.TestCase):
    """SessionRecorder.record_with_times()のテスト."""

    def test_record_with_times_saves_record(self):
        """record_with_times()で指定した時刻でレコードを保存."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime(2026, 1, 18, 10, 0, 0)

        start = datetime(2026, 1, 18, 10, 0, 0)
        end = datetime(2026, 1, 18, 10, 30, 0)
        result = recorder.record_with_times(game, start, end)

        self.assertIsNotNone(result)
        self.assertEqual(len(handler.records), 1)
        self.assertEqual(handler.records[0]['title'], "TestGame")
        # ゲームの状態は変更されない
        self.assertTrue(game.is_playing)
        self.assertEqual(game.start_time, datetime(2026, 1, 18, 10, 0, 0))

    def test_record_with_times_under_threshold_skips(self):
        """record_with_times()で5分未満のセッションはスキップ."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="TestGame", window_title="TestGame")

        start = datetime(2026, 1, 18, 10, 0, 0)
        end = datetime(2026, 1, 18, 10, 3, 0)  # 3分
        result = recorder.record_with_times(game, start, end)

        self.assertIsNone(result)
        self.assertEqual(len(handler.records), 0)


class TestWindowScannerForeground(unittest.TestCase):
    """WindowScanner.get_foreground_title()のテスト."""

    def test_get_foreground_title_returns_none_when_no_active_window(self):
        """アクティブウィンドウがない場合はNoneを返す."""
        scanner = main.WindowScanner(excluded_titles=[])
        # pygetwindow.getActiveWindow()はスタブではNoneを返す想定
        result = scanner.get_foreground_title()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
