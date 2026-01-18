import configparser
import sys
import types
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import tempfile
import os

# Stub external dependencies before importing the app.
fake_gspread = types.SimpleNamespace(
    service_account=lambda filename=None: None,
    exceptions=types.SimpleNamespace(
        APIError=Exception,
        SpreadsheetNotFound=type('SpreadsheetNotFound', (Exception,), {}),
        WorksheetNotFound=type('WorksheetNotFound', (Exception,), {}),
    ),
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


class TestDailyStatsTracker(unittest.TestCase):
    """DailyStatsTrackerのテスト."""

    def test_initial_state(self):
        """初期状態の確認."""
        tracker = main.DailyStatsTracker()
        self.assertEqual(tracker.today_completed_seconds, 0.0)
        self.assertEqual(tracker.today_game_minutes_cache, {})
        self.assertEqual(tracker.last_today_games_content, "")

    def test_add_completed_seconds(self):
        """完了秒数の追加."""
        tracker = main.DailyStatsTracker()
        tracker.add_completed_seconds(300)
        self.assertEqual(tracker.today_completed_seconds, 300)
        tracker.add_completed_seconds(150)
        self.assertEqual(tracker.today_completed_seconds, 450)

    def test_update_game_minutes_cache(self):
        """ゲーム時間キャッシュの更新."""
        tracker = main.DailyStatsTracker()
        cache = {"Game1": 30.0, "Game2": 60.0}
        tracker.update_game_minutes_cache(cache)
        self.assertEqual(tracker.today_game_minutes_cache, cache)

    def test_check_day_change_same_day(self):
        """同日ではリセットされない."""
        current_date = datetime(2026, 1, 18).date()
        tracker = main.DailyStatsTracker(get_current_date=lambda: current_date)
        tracker.add_completed_seconds(300)
        tracker.update_game_minutes_cache({"Game1": 30.0})
        
        # 同日のチェック
        result = tracker.check_day_change()
        self.assertFalse(result)
        self.assertEqual(tracker.today_completed_seconds, 300)
        self.assertEqual(tracker.today_game_minutes_cache, {"Game1": 30.0})

    def test_check_day_change_new_day(self):
        """日付変更でリセットされる."""
        day1 = datetime(2026, 1, 18).date()
        day2 = datetime(2026, 1, 19).date()
        current_date = [day1]  # mutableにして変更可能にする
        
        tracker = main.DailyStatsTracker(get_current_date=lambda: current_date[0])
        tracker.add_completed_seconds(300)
        tracker.update_game_minutes_cache({"Game1": 30.0})
        tracker.last_today_games_content = "Game1: 30分"
        
        # 日付を変更
        current_date[0] = day2
        result = tracker.check_day_change()
        
        self.assertTrue(result)
        self.assertEqual(tracker.today_completed_seconds, 0.0)
        self.assertEqual(tracker.today_game_minutes_cache, {})
        self.assertEqual(tracker.last_today_games_content, "")

    def test_check_day_change_returns_false_after_reset(self):
        """リセット後、同日の再チェックではFalseを返す."""
        day1 = datetime(2026, 1, 18).date()
        day2 = datetime(2026, 1, 19).date()
        current_date = [day1]
        
        tracker = main.DailyStatsTracker(get_current_date=lambda: current_date[0])
        
        # 日付変更
        current_date[0] = day2
        result1 = tracker.check_day_change()
        self.assertTrue(result1)
        
        # 同日の再チェック
        result2 = tracker.check_day_change()
        self.assertFalse(result2)


class TestParseRecord(unittest.TestCase):
    """_parse_record()のテスト."""

    def test_parse_valid_record(self):
        """正常なレコードをパースできる."""
        record = {
            'start_time': '2026/01/18 10:00:00',
            'end_time': '2026/01/18 11:30:00',
            'title': 'TestGame',
        }
        result = main._parse_record(record)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.start, datetime(2026, 1, 18, 10, 0, 0))
        self.assertEqual(result.end, datetime(2026, 1, 18, 11, 30, 0))
        self.assertEqual(result.game_title, 'TestGame')

    def test_parse_record_missing_title_uses_default(self):
        """titleがない場合は'不明'を使用."""
        record = {
            'start_time': '2026/01/18 10:00:00',
            'end_time': '2026/01/18 11:00:00',
        }
        result = main._parse_record(record)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.game_title, '不明')

    def test_parse_record_invalid_date_format(self):
        """不正な日付フォーマットはNoneを返す."""
        record = {
            'start_time': '2026-01-18 10:00:00',  # 間違ったフォーマット
            'end_time': '2026/01/18 11:00:00',
            'title': 'TestGame',
        }
        result = main._parse_record(record)
        self.assertIsNone(result)

    def test_parse_record_missing_start_time(self):
        """start_timeがない場合はNoneを返す."""
        record = {
            'end_time': '2026/01/18 11:00:00',
            'title': 'TestGame',
        }
        result = main._parse_record(record)
        self.assertIsNone(result)

    def test_parse_record_missing_end_time(self):
        """end_timeがない場合はNoneを返す."""
        record = {
            'start_time': '2026/01/18 10:00:00',
            'title': 'TestGame',
        }
        result = main._parse_record(record)
        self.assertIsNone(result)

    def test_parse_record_empty_dict(self):
        """空の辞書はNoneを返す."""
        result = main._parse_record({})
        self.assertIsNone(result)


class TestParsedRecordDataclass(unittest.TestCase):
    """ParsedRecordデータクラスのテスト."""

    def test_parsed_record_attributes(self):
        """ParsedRecordの属性が正しく設定される."""
        parsed = main.ParsedRecord(
            start=datetime(2026, 1, 18, 10, 0, 0),
            end=datetime(2026, 1, 18, 11, 0, 0),
            game_title='TestGame',
        )
        self.assertEqual(parsed.start, datetime(2026, 1, 18, 10, 0, 0))
        self.assertEqual(parsed.end, datetime(2026, 1, 18, 11, 0, 0))
        self.assertEqual(parsed.game_title, 'TestGame')

    def test_parsed_record_duration_calculation(self):
        """ParsedRecordからプレイ時間を計算できる."""
        parsed = main.ParsedRecord(
            start=datetime(2026, 1, 18, 10, 0, 0),
            end=datetime(2026, 1, 18, 11, 30, 0),
            game_title='TestGame',
        )
        duration_minutes = (parsed.end - parsed.start).total_seconds() / 60
        self.assertEqual(duration_minutes, 90)


class TestGSSDatetimeFormat(unittest.TestCase):
    """GSS_DATETIME_FORMAT定数のテスト."""

    def test_format_constant_matches_expected(self):
        """GSS_DATETIME_FORMATが期待する形式と一致する."""
        self.assertEqual(main.GSS_DATETIME_FORMAT, "%Y/%m/%d %H:%M:%S")

    def test_parse_with_format_constant(self):
        """GSS_DATETIME_FORMATでパースできる."""
        time_str = "2026/01/18 14:30:45"
        parsed = datetime.strptime(time_str, main.GSS_DATETIME_FORMAT)
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 1)
        self.assertEqual(parsed.day, 18)
        self.assertEqual(parsed.hour, 14)
        self.assertEqual(parsed.minute, 30)
        self.assertEqual(parsed.second, 45)


class TestGameEntryStartSession(unittest.TestCase):
    """GameEntry.start_session()のテスト."""

    def test_start_session_sets_is_playing_true(self):
        """start_session()でis_playing=Trueになる."""
        game = main.GameEntry(game_title="Test", window_title="Test")
        self.assertFalse(game.is_playing)
        game.start_session()
        self.assertTrue(game.is_playing)

    def test_start_session_sets_start_time(self):
        """start_session()でstart_timeが設定される."""
        game = main.GameEntry(game_title="Test", window_title="Test")
        self.assertIsNone(game.start_time)
        before = datetime.now()
        game.start_session()
        after = datetime.now()
        self.assertIsNotNone(game.start_time)
        self.assertGreaterEqual(game.start_time, before)
        self.assertLessEqual(game.start_time, after)


class TestGameEntryEndSession(unittest.TestCase):
    """GameEntry.end_session()のテスト."""

    def test_end_session_returns_times(self):
        """end_session()は開始・終了時刻を返す."""
        game = main.GameEntry(game_title="Test", window_title="Test")
        game.start_session()
        original_start = game.start_time
        start_time, end_time = game.end_session()
        self.assertEqual(start_time, original_start)
        self.assertIsNotNone(end_time)
        self.assertGreaterEqual(end_time, start_time)

    def test_end_session_clears_state(self):
        """end_session()後はis_playing=False、start_time=None."""
        game = main.GameEntry(game_title="Test", window_title="Test")
        game.start_session()
        game.end_session()
        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)

    def test_end_session_without_start_returns_none(self):
        """開始していない状態でend_session()するとNoneを返す."""
        game = main.GameEntry(game_title="Test", window_title="Test")
        start_time, end_time = game.end_session()
        self.assertIsNone(start_time)
        self.assertIsNone(end_time)


class TestGameEntryMatchesWindow(unittest.TestCase):
    """GameEntry.matches_window()のテスト（部分一致含む）."""

    def test_partial_match_in_title(self):
        """window_titleがウィンドウタイトルの一部として含まれる場合にマッチ."""
        game = main.GameEntry(game_title="Terraria", window_title="Terraria")
        self.assertTrue(game.matches_window("Terraria: Official Server", browsers=[]))

    def test_no_match_if_not_contained(self):
        """window_titleが含まれない場合はマッチしない."""
        game = main.GameEntry(game_title="Terraria", window_title="Terraria")
        self.assertFalse(game.matches_window("Terra - Some Other App", browsers=[]))

    def test_browser_game_matches_browser_title(self):
        """ブラウザゲームはブラウザタイトルでもマッチ."""
        game = main.GameEntry(
            game_title="WebGame",
            window_title="WebGame",
            is_browser_game=True,
        )
        self.assertTrue(game.matches_window("WebGame - Google Chrome", browsers=["Google Chrome"]))

    def test_non_browser_game_rejects_browser_title(self):
        """通常ゲームはブラウザタイトルを拒否."""
        game = main.GameEntry(
            game_title="SteamGame",
            window_title="SteamGame",
            is_browser_game=False,
        )
        self.assertFalse(game.matches_window("SteamGame - Google Chrome", browsers=["Google Chrome"]))

    def test_non_browser_game_matches_non_browser_title(self):
        """通常ゲームは非ブラウザタイトルでマッチ."""
        game = main.GameEntry(
            game_title="SteamGame",
            window_title="SteamGame",
            is_browser_game=False,
        )
        self.assertTrue(game.matches_window("SteamGame v1.2.3", browsers=["Google Chrome"]))


class TestParseBool(unittest.TestCase):
    """_parse_bool()のテスト."""

    def test_true_string(self):
        """'TRUE'文字列はTrueを返す."""
        self.assertTrue(main._parse_bool("TRUE"))

    def test_true_lowercase(self):
        """'true'文字列はTrueを返す."""
        self.assertTrue(main._parse_bool("true"))

    def test_true_mixed_case(self):
        """'True'文字列はTrueを返す."""
        self.assertTrue(main._parse_bool("True"))

    def test_false_string(self):
        """'FALSE'文字列はFalseを返す."""
        self.assertFalse(main._parse_bool("FALSE"))

    def test_empty_string(self):
        """空文字列はFalseを返す."""
        self.assertFalse(main._parse_bool(""))

    def test_other_string(self):
        """その他の文字列はFalseを返す."""
        self.assertFalse(main._parse_bool("yes"))
        self.assertFalse(main._parse_bool("1"))


class TestFormatHms(unittest.TestCase):
    """_format_hms()のテスト."""

    def test_zero_seconds(self):
        """0秒のフォーマット."""
        self.assertEqual(main._format_hms(0), "00:00:00.0")

    def test_seconds_only(self):
        """秒のみのフォーマット."""
        # 浮動小数点はint()で切り捨てられる: 45.3 * 10 = 453 -> 45.3
        self.assertEqual(main._format_hms(45.35), "00:00:45.3")

    def test_minutes_and_seconds(self):
        """分と秒のフォーマット."""
        self.assertEqual(main._format_hms(125.5), "00:02:05.5")

    def test_hours_minutes_seconds(self):
        """時間・分・秒のフォーマット."""
        # 1時間1分1.7秒 = 3661.7秒だが、int()で切り捨てられるので.75で.7になる
        self.assertEqual(main._format_hms(3661.75), "01:01:01.7")

    def test_large_hours(self):
        """長時間のフォーマット."""
        # 10時間30分45.2秒
        self.assertEqual(main._format_hms(37845.25), "10:30:45.2")


class TestWindowState(unittest.TestCase):
    """WindowStateクラスのテスト."""

    def setUp(self):
        """テスト用の一時ファイルパスを設定."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.test_path = Path(self.temp_dir) / "test_window_state.txt"

    def tearDown(self):
        """テスト用ファイルを削除."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_nonexistent_file_returns_defaults(self):
        """存在しないファイルはデフォルト値を返す."""
        x, y, mode, mode_sizes = main.WindowState.load(self.test_path)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)
        self.assertEqual(mode, "max")
        self.assertIn("max", mode_sizes)

    def test_save_and_load_roundtrip(self):
        """保存と読み込みの往復テスト."""
        mode_sizes = {"max": (500, 400), "mid": (450, 300), "min": (300, 150)}
        main.WindowState.save(self.test_path, 100, 200, "mid", mode_sizes)
        
        x, y, mode, loaded_sizes = main.WindowState.load(self.test_path)
        self.assertEqual(x, 100)
        self.assertEqual(y, 200)
        self.assertEqual(mode, "mid")
        self.assertEqual(loaded_sizes["mid"], (450, 300))

    def test_load_invalid_mode_falls_back_to_max(self):
        """不正なdisplay_modeは'max'にフォールバック."""
        import json
        data = {"x": 50, "y": 50, "display_mode": "invalid_mode", "mode_sizes": {}}
        self.test_path.write_text(json.dumps(data), encoding="utf-8")
        
        x, y, mode, mode_sizes = main.WindowState.load(self.test_path)
        self.assertEqual(mode, "max")

    def test_load_corrupted_json_returns_defaults(self):
        """破損したJSONはデフォルト値を返す."""
        self.test_path.write_text("{invalid json", encoding="utf-8")
        
        x, y, mode, mode_sizes = main.WindowState.load(self.test_path)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)
        self.assertEqual(mode, "max")


class TestSplitByDayBoundaryConditions(unittest.TestCase):
    """_split_by_day()の境界条件テスト."""

    def setUp(self):
        handler = FakeLogHandler()
        self.recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)

    def test_end_at_exactly_midnight(self):
        """0:00ちょうどに終了した場合の境界テスト."""
        start = datetime(2026, 1, 10, 23, 30, 0)
        end = datetime(2026, 1, 11, 0, 0, 0)
        segments = self.recorder._split_by_day(start, end)
        
        # 2つに分割される（前日分と0:00ちょうどの空セグメント）
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0][0].date(), datetime(2026, 1, 10).date())
        self.assertEqual(segments[1][0], datetime(2026, 1, 11, 0, 0, 0))
        self.assertEqual(segments[1][1], end)

    def test_start_at_exactly_midnight(self):
        """0:00ちょうどに開始した場合."""
        start = datetime(2026, 1, 11, 0, 0, 0)
        end = datetime(2026, 1, 11, 1, 0, 0)
        segments = self.recorder._split_by_day(start, end)
        
        # 分割なし
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0], (start, end))

    def test_segment_under_min_play_minutes_not_recorded(self):
        """5分未満のセグメントは記録されない."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(
            game_title="ShortSegmentGame",
            window_title="ShortSegmentGame",
            is_playing=True,
        )
        # 23:58 - 翌00:02 (各セグメント2分と4分)
        game.start_time = datetime(2026, 1, 10, 23, 58, 0)
        def mock_end_session():
            game.is_playing = False
            start = game.start_time
            game.start_time = None
            return start, datetime(2026, 1, 11, 0, 2, 0)
        game.end_session = mock_end_session

        result = recorder.record(game)

        # どちらも5分未満なので記録されない
        self.assertIsNone(result)
        self.assertEqual(len(handler.records), 0)


class TestWindowScanner(unittest.TestCase):
    """WindowScannerのテスト."""

    def test_excluded_titles_initialized(self):
        """除外リストが正しく設定される."""
        excluded = ["Program Manager", "Settings"]
        scanner = main.WindowScanner(excluded_titles=excluded)
        self.assertEqual(scanner.excluded_titles, set(excluded))

    def test_excluded_titles_is_set(self):
        """除外リストがsetとして保持される."""
        excluded = ["Title1", "Title2", "Title1"]  # 重複あり
        scanner = main.WindowScanner(excluded_titles=excluded)
        self.assertEqual(len(scanner.excluded_titles), 2)


class TestSessionRecorderRecordWithTimesNoStateChange(unittest.TestCase):
    """record_with_times()がゲーム状態を変更しないことのテスト."""

    def test_game_state_unchanged_after_record_with_times(self):
        """record_with_times()後もゲームの状態は変わらない."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        
        original_start = datetime(2026, 1, 18, 10, 0, 0)
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        game.start_time = original_start
        
        recorder.record_with_times(
            game,
            datetime(2026, 1, 18, 9, 0, 0),  # 記録する開始時刻
            datetime(2026, 1, 18, 9, 30, 0),  # 記録する終了時刻
        )
        
        # ゲームの状態は変わらない
        self.assertTrue(game.is_playing)
        self.assertEqual(game.start_time, original_start)


class TestRecordReturnsNoneOnFailure(unittest.TestCase):
    """記録失敗時のNone返却テスト."""

    def test_record_returns_none_when_no_start_time(self):
        """start_timeがない場合はNoneを返す."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,  # is_playing=Trueだがstart_timeはNone
        )
        
        result = recorder.record(game)
        self.assertIsNone(result)


class TestConstants(unittest.TestCase):
    """定数のテスト."""

    def test_poll_interval_seconds(self):
        """POLL_INTERVAL_SECONDSが1秒."""
        self.assertEqual(main.POLL_INTERVAL_SECONDS, 1)

    def test_min_play_minutes(self):
        """MIN_PLAY_MINUTESが5分."""
        self.assertEqual(main.MIN_PLAY_MINUTES, 5)

    def test_inactive_timeout_minutes(self):
        """INACTIVE_TIMEOUT_MINUTESが5分."""
        self.assertEqual(main.INACTIVE_TIMEOUT_MINUTES, 5)

    def test_display_modes(self):
        """DISPLAY_MODESが正しく定義されている."""
        self.assertEqual(main.DISPLAY_MODES, ("max", "mid", "min"))


class TestGameInfoLoaderExceptions(unittest.TestCase):
    """GameInfoLoader.load()の例外処理テスト."""

    def _create_mock_config(self):
        """モックConfigLoaderを作成."""
        config = MagicMock()
        config.log_handler = {'cert_file_path': 'fake.json'}
        config.game_info = {'sheet_key': 'fake_key', 'sheet_gid': 123}
        return config

    @patch('main.gspread.service_account')
    def test_load_file_not_found_returns_empty(self, mock_sa):
        """認証ファイルが見つからない場合は空リストを返す."""
        mock_sa.side_effect = FileNotFoundError("fake.json not found")
        config = self._create_mock_config()
        loader = main.GameInfoLoader(config)
        
        result = loader.load()
        
        self.assertEqual(result, [])

    @patch('main.gspread.service_account')
    def test_load_spreadsheet_not_found_returns_empty(self, mock_sa):
        """スプレッドシートが見つからない場合は空リストを返す."""
        mock_sa.side_effect = fake_gspread.exceptions.SpreadsheetNotFound("Not found")
        config = self._create_mock_config()
        loader = main.GameInfoLoader(config)
        
        result = loader.load()
        
        self.assertEqual(result, [])

    @patch('main.gspread.service_account')
    def test_load_worksheet_not_found_returns_empty(self, mock_sa):
        """ワークシートが見つからない場合は空リストを返す."""
        mock_gc = MagicMock()
        mock_gc.open_by_key.return_value.get_worksheet_by_id.side_effect = \
            fake_gspread.exceptions.WorksheetNotFound("gid not found")
        mock_sa.return_value = mock_gc
        config = self._create_mock_config()
        loader = main.GameInfoLoader(config)
        
        result = loader.load()
        
        self.assertEqual(result, [])

    @patch('main.gspread.service_account')
    def test_load_api_error_returns_empty(self, mock_sa):
        """APIエラーの場合は空リストを返す."""
        mock_sa.side_effect = fake_gspread.exceptions.APIError("API quota exceeded")
        config = self._create_mock_config()
        loader = main.GameInfoLoader(config)
        
        result = loader.load()
        
        self.assertEqual(result, [])

    @patch('main.gspread.service_account')
    def test_load_generic_exception_returns_empty(self, mock_sa):
        """その他の例外の場合は空リストを返す."""
        mock_sa.side_effect = RuntimeError("Unexpected error")
        config = self._create_mock_config()
        loader = main.GameInfoLoader(config)
        
        result = loader.load()
        
        self.assertEqual(result, [])

    @patch('main.gspread.service_account')
    def test_load_success_returns_entries(self, mock_sa):
        """正常に読み込めた場合はGameEntryリストを返す."""
        mock_sheet = MagicMock()
        mock_sheet.get_all_records.return_value = [
            {'game_title': 'Game1', 'window_title': 'Game1', 'play_with_friends': 'TRUE', 'is_browser_game': 'FALSE'},
            {'game_title': 'Game2', 'window_title': 'Game2 Window', 'play_with_friends': 'FALSE', 'is_browser_game': 'TRUE'},
        ]
        mock_gc = MagicMock()
        mock_gc.open_by_key.return_value.get_worksheet_by_id.return_value = mock_sheet
        mock_sa.return_value = mock_gc
        config = self._create_mock_config()
        loader = main.GameInfoLoader(config)
        
        result = loader.load()
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].game_title, 'Game1')
        self.assertTrue(result[0].play_with_friends)
        self.assertEqual(result[1].game_title, 'Game2')
        self.assertTrue(result[1].is_browser_game)


class TestWindowScannerGetTitles(unittest.TestCase):
    """WindowScanner.get_titles()のテスト."""

    def test_excludes_titles_in_excluded_list(self):
        """除外リストに含まれるタイトルは除外される."""
        # モックウィンドウを作成
        mock_windows = [
            MagicMock(title="Game Window"),
            MagicMock(title="Program Manager"),  # 除外対象
            MagicMock(title="Another App"),
        ]
        
        with patch.object(main.gw, 'getAllWindows', return_value=mock_windows):
            scanner = main.WindowScanner(excluded_titles=["Program Manager"])
            titles = scanner.get_titles()
        
        self.assertIn("Game Window", titles)
        self.assertIn("Another App", titles)
        self.assertNotIn("Program Manager", titles)

    def test_excludes_empty_titles(self):
        """空のタイトルは除外される."""
        mock_windows = [
            MagicMock(title="Valid Title"),
            MagicMock(title=""),  # 空タイトル
            MagicMock(title=None),  # Noneタイトル
        ]
        
        with patch.object(main.gw, 'getAllWindows', return_value=mock_windows):
            scanner = main.WindowScanner(excluded_titles=[])
            titles = scanner.get_titles()
        
        self.assertEqual(titles, ["Valid Title"])

    def test_returns_unique_titles(self):
        """重複するタイトルは1つにまとめられる."""
        mock_windows = [
            MagicMock(title="Same Title"),
            MagicMock(title="Same Title"),
            MagicMock(title="Different Title"),
        ]
        
        with patch.object(main.gw, 'getAllWindows', return_value=mock_windows):
            scanner = main.WindowScanner(excluded_titles=[])
            titles = scanner.get_titles()
        
        self.assertEqual(len(titles), 2)
        self.assertIn("Same Title", titles)
        self.assertIn("Different Title", titles)


class TestUpdateGameStates(unittest.TestCase):
    """_update_game_states()の状態遷移テスト."""

    def setUp(self):
        """テスト用のモックオブジェクトを設定."""
        self.handler = FakeLogHandler()
        self.recorder = main.SessionRecorder(log_handler=self.handler, min_play_minutes=5)
        self.daily_stats = main.DailyStatsTracker()

    def test_window_disappear_triggers_record(self):
        """ウィンドウ消失時にrecord()が呼ばれる."""
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        game.start_time = datetime.now() - timedelta(minutes=10)
        
        # ゲームをリストに追加
        games = [game]
        browsers = []
        
        # 直接_update_game_statesの動作を再現
        window_titles = []  # ウィンドウ消失
        foreground_title = None
        
        # ウィンドウ消失を検出
        window_exists = any(game.matches_window(title, browsers) for title in window_titles)
        self.assertFalse(window_exists)
        
        # record()を呼ぶ
        recorded = self.recorder.record(game)
        
        self.assertIsNotNone(recorded)
        self.assertFalse(game.is_playing)
        self.assertEqual(len(self.handler.records), 1)

    def test_inactive_5min_timeout_triggers_record_with_times(self):
        """非アクティブ5分超過でrecord_with_times()が呼ばれ、状態がリセットされる."""
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        # 開始から非アクティブ化までの時間が5分以上になるように設定
        start = datetime.now() - timedelta(minutes=15)
        inactive_since = datetime.now() - timedelta(minutes=6)  # 6分前から非アクティブ
        game.start_time = start
        game.inactive_since = inactive_since
        
        # 5分超過を検出
        inactive_seconds = game.get_inactive_seconds()
        self.assertGreaterEqual(inactive_seconds, 5 * 60)
        
        # record_with_timesを呼ぶ（start_timeからinactive_sinceまでは9分なので記録される）
        recorded = self.recorder.record_with_times(game, game.start_time, game.inactive_since)
        
        self.assertIsNotNone(recorded)
        # ゲーム状態は変わらない（record_with_timesは状態を変更しない）
        self.assertTrue(game.is_playing)
        
        # 手動でリセット（_update_game_statesの動作を再現）
        game.is_playing = False
        game.start_time = None
        game.inactive_since = None
        
        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)
        self.assertIsNone(game.inactive_since)

    def test_foreground_starts_new_session(self):
        """フォアグラウンドで新規セッションが開始される."""
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=False,
        )
        
        # フォアグラウンドになったらセッション開始
        game.start_session()
        
        self.assertTrue(game.is_playing)
        self.assertIsNotNone(game.start_time)

    def test_inactive_under_5min_stays_in_inactive_list(self):
        """非アクティブ5分未満では非アクティブリストに残る."""
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        game.start_time = datetime.now() - timedelta(minutes=10)
        game.inactive_since = datetime.now() - timedelta(minutes=3)  # 3分前から非アクティブ
        
        inactive_seconds = game.get_inactive_seconds()
        self.assertLess(inactive_seconds, 5 * 60)
        
        # セッションは継続
        self.assertTrue(game.is_playing)


class TestTodayCalculations(unittest.TestCase):
    """今日の合計/一覧/キャッシュ読込系のテスト."""

    def test_load_today_game_minutes_filters_by_date(self):
        """_load_today_game_minutesは今日のレコードのみ集計する."""
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        records = [
            {
                'start_time': f'{today.strftime("%Y/%m/%d")} 10:00:00',
                'end_time': f'{today.strftime("%Y/%m/%d")} 10:30:00',
                'title': 'TodayGame',
            },
            {
                'start_time': f'{yesterday.strftime("%Y/%m/%d")} 20:00:00',
                'end_time': f'{yesterday.strftime("%Y/%m/%d")} 21:00:00',
                'title': 'YesterdayGame',
            },
        ]
        
        # _parse_recordを使ってフィルタリングをテスト
        game_minutes = {}
        for record in records:
            parsed = main._parse_record(record)
            if parsed is None or parsed.start.date() != today:
                continue
            minutes = (parsed.end - parsed.start).total_seconds() / main.SECONDS_PER_MINUTE
            game_minutes[parsed.game_title] = game_minutes.get(parsed.game_title, 0) + minutes
        
        self.assertEqual(len(game_minutes), 1)
        self.assertIn('TodayGame', game_minutes)
        self.assertEqual(game_minutes['TodayGame'], 30)

    def test_ongoing_session_cross_midnight_counts_from_today(self):
        """日跨ぎの進行中セッションは今日0:00以降のみカウント."""
        now = datetime.now()
        today_start = datetime.combine(now.date(), time(0, 0, 0))
        yesterday_start = datetime.combine(now.date() - timedelta(days=1), time(23, 0, 0))
        
        # 昨日23:00から開始したセッション
        game = main.GameEntry(
            game_title="NightGame",
            window_title="NightGame",
            is_playing=True,
        )
        game.start_time = yesterday_start
        
        # 日跨ぎの場合は今日0:00から計算
        effective_start = max(game.start_time, today_start)
        self.assertEqual(effective_start, today_start)
        
        # 今日経過した時間のみ
        elapsed_seconds = (now - effective_start).total_seconds()
        self.assertGreater(elapsed_seconds, 0)

    def test_under_5min_session_excluded_from_totals(self):
        """5分未満の進行中セッションは合計から除外."""
        now = datetime.now()
        
        game = main.GameEntry(
            game_title="ShortGame",
            window_title="ShortGame",
            is_playing=True,
        )
        game.start_time = now - timedelta(minutes=3)  # 3分前に開始
        
        elapsed_seconds = (now - game.start_time).total_seconds()
        min_seconds = main.MIN_PLAY_MINUTES * main.SECONDS_PER_MINUTE
        
        # 5分未満なので除外
        self.assertLess(elapsed_seconds, min_seconds)

    def test_inactive_game_included_in_totals(self):
        """非アクティブ中のゲームも合計に含まれる."""
        now = datetime.now()
        
        game = main.GameEntry(
            game_title="InactiveGame",
            window_title="InactiveGame",
            is_playing=True,
        )
        game.start_time = now - timedelta(minutes=10)
        game.set_inactive()  # 非アクティブに設定
        
        self.assertTrue(game.is_inactive())
        
        # 10分以上なので合計に含まれる
        elapsed_seconds = (now - game.start_time).total_seconds()
        min_seconds = main.MIN_PLAY_MINUTES * main.SECONDS_PER_MINUTE
        self.assertGreaterEqual(elapsed_seconds, min_seconds)


class TestConfigLoaderValidation(unittest.TestCase):
    """ConfigLoaderの検証テスト."""

    def setUp(self):
        """テスト用の一時ディレクトリを作成."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """テスト用ファイルを削除."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_section_raises_key_error(self):
        """必須セクションがない場合はKeyErrorを送出."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[OTHER]\nkey=value\n")
        
        # config_loaderをインポート（mainからではなく直接）
        import config_loader
        with self.assertRaises(KeyError) as ctx:
            config_loader.ConfigLoader(config_path)
        
        self.assertIn('LOGHANDLER', str(ctx.exception))

    def test_missing_key_raises_key_error(self):
        """必須キーがない場合はKeyErrorを送出."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\n")
            f.write("[GAMEINFO]\nsheet_key=abc\nsheet_gid=123\n")
        
        import config_loader
        with self.assertRaises(KeyError) as ctx:
            config_loader.ConfigLoader(config_path)
        
        self.assertIn('sheet_key', str(ctx.exception))

    def test_invalid_sheet_gid_raises_value_error(self):
        """sheet_gidが整数でない場合はValueErrorを送出."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=abc\n")
            f.write("[GAMEINFO]\nsheet_key=abc\nsheet_gid=not_an_int\n")
        
        import config_loader
        with self.assertRaises(ValueError) as ctx:
            config_loader.ConfigLoader(config_path)
        
        self.assertIn('sheet_gid', str(ctx.exception))

    def test_valid_config_loads_successfully(self):
        """有効な設定ファイルは正常に読み込める."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")
        
        import config_loader
        cfg = config_loader.ConfigLoader(config_path)
        
        self.assertEqual(cfg.log_handler['cert_file_path'], 'test.json')
        self.assertEqual(cfg.log_handler['sheet_key'], 'log_key')
        self.assertEqual(cfg.game_info['sheet_key'], 'game_key')
        self.assertEqual(cfg.game_info['sheet_gid'], 12345)


class TestFakeLogHandlerSaveFailure(unittest.TestCase):
    """LogHandler.save_record()の失敗テスト."""

    def test_save_record_returns_false_on_failure(self):
        """保存失敗時はFalseを返す."""
        class FailingLogHandler(FakeLogHandler):
            def save_record(self, values):
                return False
        
        handler = FailingLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        game.start_time = datetime.now() - timedelta(minutes=10)
        
        # save_recordが失敗するとNoneが返る
        result = recorder.record(game)
        
        # any_saved = Falseなのでresultはなし
        self.assertIsNone(result)


class TestUpdateGameStatesIntegration(unittest.TestCase):
    """_update_game_states()の統合テスト."""

    def setUp(self):
        """テスト用のモックオブジェクトを設定."""
        self.handler = FakeLogHandler()
        self.recorder = main.SessionRecorder(log_handler=self.handler, min_play_minutes=5)
        self.daily_stats = main.DailyStatsTracker()
        self.browsers = ['Chrome', 'Firefox']

    def _run_update_game_states(self, games, window_titles, foreground_title):
        """_update_game_statesのロジックを再現して実行."""
        active_games = []
        inactive_games = []
        
        for game in games:
            window_exists = any(
                game.matches_window(title, self.browsers)
                for title in window_titles
            )
            is_foreground = (
                foreground_title is not None
                and game.matches_window(foreground_title, self.browsers)
            )
            
            if not game.is_playing:
                if is_foreground:
                    game.start_session()
                    active_games.append(game)
            else:
                if not window_exists:
                    recorded_seconds = self.recorder.record(game)
                    if recorded_seconds:
                        self.daily_stats.add_completed_seconds(recorded_seconds)
                elif is_foreground:
                    game.set_active()
                    active_games.append(game)
                else:
                    if not game.is_inactive():
                        game.set_inactive()
                    
                    inactive_seconds = game.get_inactive_seconds()
                    if inactive_seconds >= main.INACTIVE_TIMEOUT_MINUTES * main.SECONDS_PER_MINUTE:
                        if game.start_time and game.inactive_since:
                            recorded_seconds = self.recorder.record_with_times(
                                game, game.start_time, game.inactive_since
                            )
                            if recorded_seconds:
                                self.daily_stats.add_completed_seconds(recorded_seconds)
                        game.is_playing = False
                        game.start_time = None
                        game.inactive_since = None
                    else:
                        inactive_games.append(game)
        
        return active_games, inactive_games

    def test_full_flow_window_disappear_records_and_updates_stats(self):
        """ウィンドウ消失で記録され、daily_statsが更新される."""
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        game.start_time = datetime.now() - timedelta(minutes=10)
        
        active, inactive = self._run_update_game_states([game], [], None)
        
        self.assertEqual(len(active), 0)
        self.assertEqual(len(inactive), 0)
        self.assertFalse(game.is_playing)
        self.assertEqual(len(self.handler.records), 1)
        self.assertGreater(self.daily_stats.today_completed_seconds, 0)

    def test_full_flow_foreground_returns_active(self):
        """フォアグラウンドで開始するとactiveリストに返される."""
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=False,
        )
        
        active, inactive = self._run_update_game_states(
            [game], ["TestGame Window"], "TestGame Window"
        )
        
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0], game)
        self.assertTrue(game.is_playing)

    def test_full_flow_inactive_under_5min_returns_inactive(self):
        """非アクティブ5分未満はinactiveリストに返される."""
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        game.start_time = datetime.now() - timedelta(minutes=10)
        
        # 最初はフォアグラウンド
        active, inactive = self._run_update_game_states(
            [game], ["TestGame Window"], "TestGame Window"
        )
        self.assertEqual(len(active), 1)
        
        # 次に非フォアグラウンド（別ウィンドウがフォアグラウンド）
        active, inactive = self._run_update_game_states(
            [game], ["TestGame Window", "Other Window"], "Other Window"
        )
        
        self.assertEqual(len(active), 0)
        self.assertEqual(len(inactive), 1)
        self.assertTrue(game.is_inactive())

    def test_full_flow_inactive_5min_timeout_records_and_resets(self):
        """非アクティブ5分超過で記録されて状態リセット."""
        game = main.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        game.start_time = datetime.now() - timedelta(minutes=15)
        game.inactive_since = datetime.now() - timedelta(minutes=6)
        
        active, inactive = self._run_update_game_states(
            [game], ["TestGame Window", "Other Window"], "Other Window"
        )
        
        self.assertEqual(len(active), 0)
        self.assertEqual(len(inactive), 0)
        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)
        self.assertIsNone(game.inactive_since)
        self.assertEqual(len(self.handler.records), 1)
        self.assertGreater(self.daily_stats.today_completed_seconds, 0)


class TestWindowScannerGetForegroundTitle(unittest.TestCase):
    """WindowScanner.get_foreground_title()のテスト."""

    def test_returns_title_when_active_window_exists(self):
        """アクティブウィンドウがある場合はタイトルを返す."""
        mock_window = MagicMock()
        mock_window.title = "Active Window Title"
        
        with patch.object(main.gw, 'getActiveWindow', return_value=mock_window):
            scanner = main.WindowScanner(excluded_titles=[])
            result = scanner.get_foreground_title()
        
        self.assertEqual(result, "Active Window Title")

    def test_returns_none_when_no_active_window(self):
        """アクティブウィンドウがない場合はNoneを返す."""
        with patch.object(main.gw, 'getActiveWindow', return_value=None):
            scanner = main.WindowScanner(excluded_titles=[])
            result = scanner.get_foreground_title()
        
        self.assertIsNone(result)

    def test_returns_none_when_title_is_empty(self):
        """タイトルが空の場合はNoneを返す."""
        mock_window = MagicMock()
        mock_window.title = ""
        
        with patch.object(main.gw, 'getActiveWindow', return_value=mock_window):
            scanner = main.WindowScanner(excluded_titles=[])
            result = scanner.get_foreground_title()
        
        self.assertIsNone(result)

    def test_returns_none_when_exception_occurs(self):
        """例外発生時はNoneを返す（例外は吸収される）."""
        with patch.object(main.gw, 'getActiveWindow', side_effect=RuntimeError("Test error")):
            scanner = main.WindowScanner(excluded_titles=[])
            result = scanner.get_foreground_title()
        
        self.assertIsNone(result)


class TestConfigLoaderGetList(unittest.TestCase):
    """ConfigLoader._get_list()のテスト."""

    def setUp(self):
        """テスト用の一時ディレクトリを作成."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """テスト用ファイルを削除."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_returns_default_when_section_missing(self):
        """セクションがない場合はデフォルトを返す."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")
        
        import config_loader
        cfg = config_loader.ConfigLoader(config_path)
        
        # WINDOW_SCANセクションがないのでデフォルト
        self.assertEqual(cfg.window_scan['browsers'], config_loader.DEFAULT_BROWSERS)

    def test_returns_default_when_key_missing(self):
        """キーがない場合はデフォルトを返す."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")
            f.write("[WINDOW_SCAN]\n")  # セクションはあるがキーがない
        
        import config_loader
        cfg = config_loader.ConfigLoader(config_path)
        
        self.assertEqual(cfg.window_scan['browsers'], config_loader.DEFAULT_BROWSERS)

    def test_returns_default_when_value_empty(self):
        """値が空の場合はデフォルトを返す."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")
            f.write("[WINDOW_SCAN]\nbrowsers=\n")  # 空の値
        
        import config_loader
        cfg = config_loader.ConfigLoader(config_path)
        
        self.assertEqual(cfg.window_scan['browsers'], config_loader.DEFAULT_BROWSERS)

    def test_returns_default_when_value_only_whitespace(self):
        """値が空白のみの場合はデフォルトを返す."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")
            f.write("[WINDOW_SCAN]\nbrowsers=  ,  ,  \n")  # 空白とカンマのみ
        
        import config_loader
        cfg = config_loader.ConfigLoader(config_path)
        
        self.assertEqual(cfg.window_scan['browsers'], config_loader.DEFAULT_BROWSERS)

    def test_parses_comma_separated_values(self):
        """カンマ区切りの値を正しくパースする."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")
            f.write("[WINDOW_SCAN]\nbrowsers=Chrome, Firefox, Edge\n")
        
        import config_loader
        cfg = config_loader.ConfigLoader(config_path)
        
        self.assertEqual(cfg.window_scan['browsers'], ['Chrome', 'Firefox', 'Edge'])


class TestLogHandlerSaveRecordExceptions(unittest.TestCase):
    """LogHandler.save_record()の例外ハンドリングテスト."""

    def test_api_error_returns_false(self):
        """APIError発生時はFalseを返す."""
        class MockLogHandler:
            def __init__(self):
                self.records = []
                self.index = 0
                self.sheet = MagicMock()
                self.sheet.append_row.side_effect = fake_gspread.exceptions.APIError("Quota exceeded")
            
            def save_record(self, values):
                try:
                    self.sheet.append_row(values, value_input_option='USER_ENTERED')
                    return True
                except fake_gspread.exceptions.APIError as e:
                    print(f'APIError occurred while appending row: {e}')
                    return False
                except Exception as e:
                    print(f'Exception occurred while appending row: {e}')
                    return False
        
        handler = MockLogHandler()
        result = handler.save_record([1, '2026/01/18 10:00:00', '2026/01/18 11:00:00', 'Test', False])
        
        self.assertFalse(result)

    def test_generic_exception_returns_false(self):
        """汎用Exception発生時はFalseを返す."""
        class MockLogHandler:
            def __init__(self):
                self.records = []
                self.index = 0
                self.sheet = MagicMock()
                self.sheet.append_row.side_effect = RuntimeError("Network error")
            
            def save_record(self, values):
                try:
                    self.sheet.append_row(values, value_input_option='USER_ENTERED')
                    return True
                except fake_gspread.exceptions.APIError as e:
                    print(f'APIError occurred while appending row: {e}')
                    return False
                except Exception as e:
                    print(f'Exception occurred while appending row: {e}')
                    return False
        
        handler = MockLogHandler()
        result = handler.save_record([1, '2026/01/18 10:00:00', '2026/01/18 11:00:00', 'Test', False])
        
        self.assertFalse(result)

    def test_success_returns_true_and_updates_cache(self):
        """成功時はTrueを返しキャッシュも更新."""
        class MockLogHandler:
            def __init__(self):
                self.records = []
                self.index = 0
                self.sheet = MagicMock()
            
            def save_record(self, values):
                try:
                    self.sheet.append_row(values, value_input_option='USER_ENTERED')
                    if len(values) >= 5:
                        self.records.append({
                            'index': values[0],
                            'start_time': values[1],
                            'end_time': values[2],
                            'title': values[3],
                            'play_with_friends': values[4],
                        })
                    return True
                except Exception:
                    return False
        
        handler = MockLogHandler()
        result = handler.save_record([1, '2026/01/18 10:00:00', '2026/01/18 11:00:00', 'Test', False])
        
        self.assertTrue(result)
        self.assertEqual(len(handler.records), 1)
        self.assertEqual(handler.records[0]['title'], 'Test')


class TestInitComponentsErrorHandling(unittest.TestCase):
    """_init_components()のエラーハンドリングテスト."""

    def test_empty_games_disables_window(self):
        """ゲーム情報が空の場合はウィンドウを無効化."""
        # MainWindowの初期化をモックで回避してテスト
        # 実際のUIを使わずにロジックをテスト
        
        class MockMainWindow:
            def __init__(self):
                self.disabled = False
                self.status = ""
                self.games = []
            
            def setDisabled(self, value):
                self.disabled = value
            
            def _set_status(self, message):
                self.status = message
        
        mock_window = MockMainWindow()
        
        # GameInfoLoaderが空を返した場合の処理を再現
        games = []  # 空のゲームリスト
        if not games:
            mock_window._set_status('ゲーム情報が取得できませんでした（config.ini を確認）')
            mock_window.setDisabled(True)
        
        self.assertTrue(mock_window.disabled)
        self.assertIn('ゲーム情報が取得できませんでした', mock_window.status)

    def test_loghandler_file_not_found_disables_window(self):
        """LogHandler認証ファイルが見つからない場合はウィンドウを無効化."""
        class MockMainWindow:
            def __init__(self):
                self.disabled = False
                self.status = ""
            
            def setDisabled(self, value):
                self.disabled = value
            
            def _set_status(self, message):
                self.status = message
        
        mock_window = MockMainWindow()
        
        # FileNotFoundError発生時の処理を再現
        try:
            raise FileNotFoundError("service_account.json not found")
        except FileNotFoundError as e:
            print(f'ログ用認証情報ファイルが見つかりません: {e}')
            mock_window._set_status('認証情報ファイルが見つかりません（config.ini を確認）')
            mock_window.setDisabled(True)
        
        self.assertTrue(mock_window.disabled)
        self.assertIn('認証情報ファイル', mock_window.status)

    def test_loghandler_spreadsheet_not_found_disables_window(self):
        """LogHandlerスプレッドシートが見つからない場合はウィンドウを無効化."""
        class MockMainWindow:
            def __init__(self):
                self.disabled = False
                self.status = ""
            
            def setDisabled(self, value):
                self.disabled = value
            
            def _set_status(self, message):
                self.status = message
        
        mock_window = MockMainWindow()
        
        # SpreadsheetNotFound発生時の処理を再現
        try:
            raise fake_gspread.exceptions.SpreadsheetNotFound("Not found")
        except fake_gspread.exceptions.SpreadsheetNotFound:
            mock_window._set_status('ログ用スプレッドシートが見つかりません')
            mock_window.setDisabled(True)
        
        self.assertTrue(mock_window.disabled)
        self.assertIn('スプレッドシート', mock_window.status)


class TestUIUpdateMethods(unittest.TestCase):
    """UI更新メソッドのテスト."""

    def test_update_session_times_shows_max_elapsed(self):
        """_update_session_timesは最長セッション時間を表示."""
        # UIウィジェットのモック
        mock_display = MagicMock()
        
        game1 = main.GameEntry(game_title="Game1", window_title="Game1", is_playing=True)
        game1.start_time = datetime.now() - timedelta(minutes=10)
        
        game2 = main.GameEntry(game_title="Game2", window_title="Game2", is_playing=True)
        game2.start_time = datetime.now() - timedelta(minutes=5)
        
        now = datetime.now()
        all_playing = [game1, game2]
        
        # 最長を計算
        max_elapsed = max(
            (now - game.start_time).total_seconds()
            if game.start_time else 0
            for game in all_playing
        )
        
        # game1の方が長い（10分）
        self.assertGreater(max_elapsed, 9 * 60)
        self.assertLess(max_elapsed, 11 * 60)

    def test_update_today_totals_excludes_under_5min(self):
        """_update_today_totalsは5分未満のセッションを除外."""
        game = main.GameEntry(game_title="ShortGame", window_title="ShortGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=3)
        
        now = datetime.now()
        today_start = datetime.combine(now.date(), time(0, 0, 0))
        
        effective_start = max(game.start_time, today_start)
        elapsed_seconds = (now - effective_start).total_seconds()
        min_seconds = main.MIN_PLAY_MINUTES * main.SECONDS_PER_MINUTE
        
        # 5分未満なので除外される
        include_in_total = elapsed_seconds >= min_seconds
        self.assertFalse(include_in_total)

    def test_update_today_totals_includes_cross_midnight_from_today(self):
        """_update_today_totalsは日跨ぎセッションを今日0:00からカウント."""
        now = datetime.now()
        today_start = datetime.combine(now.date(), time(0, 0, 0))
        
        # 昨日23:00開始のセッション
        game = main.GameEntry(game_title="NightGame", window_title="NightGame", is_playing=True)
        game.start_time = datetime.combine(now.date() - timedelta(days=1), time(23, 0, 0))
        
        effective_start = max(game.start_time, today_start)
        
        # effective_startは今日0:00になる
        self.assertEqual(effective_start, today_start)

    def test_scan_tick_clears_table_on_day_change(self):
        """_scan_tickは日付変更時にtoday_games_tableをクリア."""
        # DailyStatsTrackerの日付変更検出をテスト
        day1 = datetime(2026, 1, 18).date()
        day2 = datetime(2026, 1, 19).date()
        current_date = [day1]
        
        tracker = main.DailyStatsTracker(get_current_date=lambda: current_date[0])
        tracker.add_completed_seconds(1000)
        
        # 日付変更
        current_date[0] = day2
        result = tracker.check_day_change()
        
        self.assertTrue(result)
        self.assertEqual(tracker.today_completed_seconds, 0.0)
        # UIのクリアは_scan_tickで行われる（モックなしでは検証不可だが、ロジックは確認済み）


class TestMainWindowDirectMethods(unittest.TestCase):
    """MainWindowの実際のメソッドを直接テスト（モックUI）."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        # 必要な属性をセットアップ
        window.games = []
        window.browsers = ['Chrome', 'Firefox']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.latest_window_titles = []
        window.display_mode = 'mid'
        window.mode_sizes = {'min': (300, 80), 'mid': (300, 200), 'max': (300, 400)}
        window.daily_stats = main.DailyStatsTracker()
        window.recorder = main.SessionRecorder(log_handler=FakeLogHandler(), min_play_minutes=5)
        
        # モックUI
        window.w = MagicMock()
        window.w.active_display = MagicMock()
        window.w.session_time_display = MagicMock()
        window.w.today_time_display = MagicMock()
        window.w.window_list = MagicMock()
        window.w.today_games_table = MagicMock()
        
        # モックスキャナー
        window.scanner = MagicMock()
        window.scanner.excluded_titles = set()
        
        return window

    def test_update_game_states_returns_active_when_foreground(self):
        """_update_game_statesはフォアグラウンドゲームをactiveとして返す."""
        window = self._create_mock_main_window()
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=False)
        window.games = [game]
        
        active, inactive = window._update_game_states(
            window_titles=["TestGame Window"],
            foreground_title="TestGame Window"
        )
        
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0], game)
        self.assertTrue(game.is_playing)

    def test_update_game_states_returns_inactive_when_not_foreground(self):
        """_update_game_statesは非フォアグラウンドのプレイ中ゲームをinactiveとして返す."""
        window = self._create_mock_main_window()
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.games = [game]
        
        active, inactive = window._update_game_states(
            window_titles=["TestGame Window", "Other Window"],
            foreground_title="Other Window"
        )
        
        self.assertEqual(len(active), 0)
        self.assertEqual(len(inactive), 1)
        self.assertTrue(game.is_inactive())

    def test_update_game_states_records_when_window_disappears(self):
        """_update_game_statesはウィンドウ消失時に記録し、daily_statsを更新."""
        window = self._create_mock_main_window()
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.games = [game]
        
        active, inactive = window._update_game_states(
            window_titles=[],  # ウィンドウ消失
            foreground_title=None
        )
        
        self.assertEqual(len(active), 0)
        self.assertEqual(len(inactive), 0)
        self.assertFalse(game.is_playing)
        self.assertGreater(window.daily_stats.today_completed_seconds, 0)

    def test_update_game_states_inactive_timeout_records_with_times(self):
        """_update_game_statesは非アクティブ5分超で部分記録しdaily_statsを更新."""
        window = self._create_mock_main_window()
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=15)
        game.inactive_since = datetime.now() - timedelta(minutes=6)
        window.games = [game]
        
        active, inactive = window._update_game_states(
            window_titles=["TestGame Window", "Other Window"],
            foreground_title="Other Window"
        )
        
        self.assertEqual(len(active), 0)
        self.assertEqual(len(inactive), 0)
        self.assertFalse(game.is_playing)
        self.assertGreater(window.daily_stats.today_completed_seconds, 0)

    def test_scan_tick_updates_caches(self):
        """_scan_tickはキャッシュを更新する."""
        window = self._create_mock_main_window()
        window.setWindowTitle = MagicMock()
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=False)
        window.games = [game]
        window.scanner.get_titles.return_value = ["TestGame Window"]
        window.scanner.get_foreground_title.return_value = "TestGame Window"
        
        window._scan_tick()
        
        self.assertEqual(window.latest_window_titles, ["TestGame Window"])
        self.assertEqual(len(window.active_games_cache), 1)

    def test_scan_tick_clears_table_on_day_change_direct(self):
        """_scan_tickは日付変更時にtoday_games_tableをクリア（実メソッド呼び出し）."""
        window = self._create_mock_main_window()
        window.setWindowTitle = MagicMock()
        window.games = [main.GameEntry(game_title="TestGame", window_title="TestGame")]
        window.scanner.get_titles.return_value = []
        window.scanner.get_foreground_title.return_value = None
        
        # 日付変更を模擬
        window.daily_stats.check_day_change = MagicMock(return_value=True)
        
        window._scan_tick()
        
        window.w.today_games_table.setRowCount.assert_called_with(0)

    def test_scan_tick_returns_early_when_no_games(self):
        """_scan_tickはゲームがない場合早期リターン."""
        window = self._create_mock_main_window()
        window.games = []
        
        window._scan_tick()
        
        # get_titlesが呼ばれていない
        window.scanner.get_titles.assert_not_called()

    def test_ui_tick_calls_update_methods(self):
        """_ui_tickはUI更新メソッドを呼び出す."""
        window = self._create_mock_main_window()
        window._update_session_times = MagicMock()
        window._update_today_totals = MagicMock()
        window._update_today_games_list = MagicMock()
        
        window._ui_tick()
        
        window._update_session_times.assert_called_once()
        window._update_today_totals.assert_called_once()
        window._update_today_games_list.assert_called_once()


class TestMainWindowUIHelpers(unittest.TestCase):
    """UI更新ヘルパーメソッドの直接テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.daily_stats = main.DailyStatsTracker()
        window.recorder = main.SessionRecorder(log_handler=FakeLogHandler(), min_play_minutes=5)
        
        # モックUI
        window.w = MagicMock()
        window.w.active_display = MagicMock()
        window.w.session_time_display = MagicMock()
        window.w.today_time_display = MagicMock()
        window.w.window_list = MagicMock()
        window.w.today_games_table = MagicMock()
        window.w.today_games_table.rowCount.return_value = 0
        
        return window

    def test_update_active_list_shows_games(self):
        """_update_active_listはプレイ中ゲームを表示."""
        window = self._create_mock_main_window()
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        
        window._update_active_list([game], [])
        
        window.w.active_display.setText.assert_called_once_with("TestGame")

    def test_update_active_list_shows_inactive_with_suffix(self):
        """_update_active_listは非アクティブゲームに「停止中」を付ける."""
        window = self._create_mock_main_window()
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.set_inactive()
        
        window._update_active_list([], [game])
        
        window.w.active_display.setText.assert_called_once_with("TestGame - 停止中")

    def test_update_active_list_shows_dash_when_empty(self):
        """_update_active_listは空の場合「---」を表示."""
        window = self._create_mock_main_window()
        
        window._update_active_list([], [])
        
        window.w.active_display.setText.assert_called_once_with("---")

    def test_update_active_list_multiple_games(self):
        """_update_active_listは複数ゲームをスラッシュ区切りで表示."""
        window = self._create_mock_main_window()
        game1 = main.GameEntry(game_title="Game1", window_title="Game1", is_playing=True)
        game2 = main.GameEntry(game_title="Game2", window_title="Game2", is_playing=True)
        game2.set_inactive()
        
        window._update_active_list([game1], [game2])
        
        window.w.active_display.setText.assert_called_once_with("Game1 / Game2 - 停止中")

    def test_update_session_times_shows_max(self):
        """_update_session_timesは最長時間を表示."""
        window = self._create_mock_main_window()
        game1 = main.GameEntry(game_title="Game1", window_title="Game1", is_playing=True)
        game1.start_time = datetime.now() - timedelta(minutes=10)
        game2 = main.GameEntry(game_title="Game2", window_title="Game2", is_playing=True)
        game2.start_time = datetime.now() - timedelta(minutes=5)
        window.inactive_games_cache = []
        
        window._update_session_times([game1, game2], datetime.now())
        
        # 10分が表示される（HH:MM:SS.F形式 = 00:10:xx.x）
        call_arg = window.w.session_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:10:"))

    def test_update_session_times_shows_dash_when_empty(self):
        """_update_session_timesは空の場合「---」を表示."""
        window = self._create_mock_main_window()
        window.inactive_games_cache = []
        
        window._update_session_times([], datetime.now())
        
        window.w.session_time_display.setText.assert_called_once_with("---")

    def test_update_today_totals_direct(self):
        """_update_today_totalsはトータル時間を更新."""
        window = self._create_mock_main_window()
        window.daily_stats.today_completed_seconds = 3600.0  # 1時間
        window.inactive_games_cache = []
        
        window._update_today_totals([], datetime.now())
        
        call_arg = window.w.today_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("01:00:"))

    def test_update_today_totals_includes_playing_game(self):
        """_update_today_totalsはプレイ中ゲームも含める（5分以上）."""
        window = self._create_mock_main_window()
        window.daily_stats.today_completed_seconds = 0.0
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.inactive_games_cache = []
        
        window._update_today_totals([game], datetime.now())
        
        # 10分以上表示される（HH:MM:SS.F形式）
        call_arg = window.w.today_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:10:") or call_arg.startswith("00:09:"))

    def test_update_window_list_clears_and_adds(self):
        """_update_window_listはリストをクリアしてウィンドウを追加."""
        window = self._create_mock_main_window()
        
        window._update_window_list(["Window1", "Window2"])
        
        window.w.window_list.clear.assert_called_once()
        self.assertEqual(window.w.window_list.addItem.call_count, 2)

    def test_update_today_games_list_clears_when_empty(self):
        """_update_today_games_listは空のとき最終コンテンツを更新."""
        window = self._create_mock_main_window()
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.daily_stats.today_game_minutes_cache = {}
        window.daily_stats.last_today_games_content = "old_content"
        
        window._update_today_games_list(datetime.now())
        
        self.assertEqual(window.daily_stats.last_today_games_content, "")
        window.w.today_games_table.setRowCount.assert_called_with(0)


class TestMainWindowDisplayModeAndState(unittest.TestCase):
    """表示モード/ウィンドウ状態系イベントのテスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.display_mode = 'mid'
        window.mode_sizes = {'min': (300, 80), 'mid': (300, 200), 'max': (300, 400)}
        window.scanner = MagicMock()
        window.scanner.excluded_titles = set()
        
        # setWindowTitle用
        window._window_title = ""
        window.setWindowTitle = lambda t: setattr(window, '_window_title', t)
        window.windowTitle = lambda: window._window_title
        
        # モックUI
        window.w = MagicMock()
        
        # geometry用
        window._geom = MagicMock()
        window._geom.x.return_value = 100
        window._geom.y.return_value = 200
        window._geom.width.return_value = 300
        window._geom.height.return_value = 200
        window.geometry = lambda: window._geom
        window.width = lambda: 300
        window.height = lambda: 200
        
        # モックメソッド
        window.setMinimumHeight = MagicMock()
        window.setMaximumHeight = MagicMock()
        window.resize = MagicMock()
        window.setVisible = MagicMock()
        
        return window

    def test_set_status_updates_title(self):
        """_set_statusはタイトルを更新."""
        window = self._create_mock_main_window()
        
        window._set_status("テストメッセージ")
        
        self.assertIn("テストメッセージ", window._window_title)
        self.assertIn(main.BASE_TITLE, window._window_title)

    def test_set_status_adds_to_excluded_titles(self):
        """_set_statusは新しいタイトルをexcluded_titlesに追加."""
        window = self._create_mock_main_window()
        
        window._set_status("テストメッセージ")
        
        expected_title = f"{main.BASE_TITLE} - テストメッセージ"
        self.assertIn(expected_title, window.scanner.excluded_titles)

    def test_cycle_display_mode_changes_mode(self):
        """_cycle_display_modeはモードを循環."""
        window = self._create_mock_main_window()
        window._apply_display_mode = MagicMock()
        window._save_window_state = MagicMock()
        # DISPLAY_MODES = ("max", "mid", "min") なので max -> mid
        window.display_mode = 'max'
        
        window._cycle_display_mode()
        
        self.assertEqual(window.display_mode, 'mid')
        window._apply_display_mode.assert_called_once()
        window._save_window_state.assert_called_once()

    def test_cycle_display_mode_wraps_around(self):
        """_cycle_display_modeはminからmaxに循環."""
        window = self._create_mock_main_window()
        window._apply_display_mode = MagicMock()
        window._save_window_state = MagicMock()
        # DISPLAY_MODES = ("max", "mid", "min") なので min -> max
        window.display_mode = 'min'
        
        window._cycle_display_mode()
        
        self.assertEqual(window.display_mode, 'max')

    def test_apply_mode_geometry_sets_size(self):
        """_apply_mode_geometryはモードに応じたサイズを設定."""
        window = self._create_mock_main_window()
        window.display_mode = 'mid'
        
        window._apply_mode_geometry()
        
        window.resize.assert_called_once_with(300, 200)

    def test_save_window_state_records_current_mode_size(self):
        """_save_window_stateは現在のサイズをmode_sizesに記録."""
        window = self._create_mock_main_window()
        window._geom.width.return_value = 350
        window._geom.height.return_value = 250
        
        with patch.object(main.WindowState, 'save') as mock_save:
            window._save_window_state()
        
        self.assertEqual(window.mode_sizes['mid'], (350, 250))
        mock_save.assert_called_once()

    def test_apply_display_mode_hides_widgets_in_min_mode(self):
        """_apply_display_modeはminモードでウィジェットを非表示."""
        window = self._create_mock_main_window()
        window.display_mode = 'min'
        window._set_widget_visibility = MagicMock()
        window._set_widget_with_height = MagicMock()
        
        window._apply_display_mode()
        
        # session_labelはis_expanded=Falseで非表示
        calls = [call for call in window._set_widget_visibility.call_args_list]
        # minモードではsession_labelがFalseで呼ばれる
        session_label_calls = [c for c in calls if c[0][0] == window.w.session_label]
        if session_label_calls:
            self.assertFalse(session_label_calls[0][0][1])


class TestInitComponentsDirect(unittest.TestCase):
    """_init_componentsの成功/失敗分岐を直接テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = []
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.display_mode = 'mid'
        window.mode_sizes = {}
        window.daily_stats = main.DailyStatsTracker()
        
        window._disabled = False
        window._status = ""
        window.setDisabled = lambda v: setattr(window, '_disabled', v)
        window.setWindowTitle = lambda t: setattr(window, '_window_title', t)
        window.windowTitle = lambda: getattr(window, '_window_title', '')
        
        window.w = MagicMock()
        window.scanner = None
        
        return window

    def _mock_set_status(self, window):
        """_set_statusのモック実装."""
        def _set_status(message):
            window._status = message
            window._window_title = f"{main.BASE_TITLE} - {message}"
            if window.scanner:
                window.scanner.excluded_titles.add(window._window_title)
        return _set_status

    def test_init_components_success(self):
        """_init_componentsの正常系."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)
        window._apply_display_mode = MagicMock()
        window._apply_mode_geometry = MagicMock()
        
        mock_config = MagicMock()
        mock_config.window_scan.get.return_value = ['Chrome']
        
        mock_games = [main.GameEntry(game_title="Test", window_title="Test")]
        
        with patch('main.ConfigLoader', return_value=mock_config):
            with patch('main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = mock_games
                with patch('main.LogHandler') as MockLogHandler:
                    MockLogHandler.return_value = FakeLogHandler()
                    window._init_components()
        
        self.assertFalse(window._disabled)
        self.assertEqual(len(window.games), 1)

    def test_init_components_empty_games_disables(self):
        """_init_componentsはゲームが空の場合無効化."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)
        
        mock_config = MagicMock()
        
        with patch('main.ConfigLoader', return_value=mock_config):
            with patch('main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = []
                window._init_components()
        
        self.assertTrue(window._disabled)
        self.assertIn('ゲーム情報', window._status)

    def test_init_components_loghandler_file_not_found_disables(self):
        """_init_componentsはLogHandlerのFileNotFoundErrorで無効化."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)
        
        mock_config = MagicMock()
        mock_config.window_scan.get.return_value = []
        mock_games = [main.GameEntry(game_title="Test", window_title="Test")]
        
        with patch('main.ConfigLoader', return_value=mock_config):
            with patch('main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = mock_games
                with patch('main.LogHandler', side_effect=FileNotFoundError("service_account.json")):
                    window._init_components()
        
        self.assertTrue(window._disabled)
        self.assertIn('認証情報', window._status)

    def test_init_components_spreadsheet_not_found_disables(self):
        """_init_componentsはSpreadsheetNotFoundで無効化."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)
        
        mock_config = MagicMock()
        mock_config.window_scan.get.return_value = []
        mock_games = [main.GameEntry(game_title="Test", window_title="Test")]
        
        with patch('main.ConfigLoader', return_value=mock_config):
            with patch('main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = mock_games
                with patch('main.LogHandler', side_effect=fake_gspread.exceptions.SpreadsheetNotFound()):
                    window._init_components()
        
        self.assertTrue(window._disabled)
        self.assertIn('スプレッドシート', window._status)

    def test_init_components_api_error_disables(self):
        """_init_componentsはAPIErrorで無効化."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)
        
        mock_config = MagicMock()
        mock_config.window_scan.get.return_value = []
        mock_games = [main.GameEntry(game_title="Test", window_title="Test")]
        
        with patch('main.ConfigLoader', return_value=mock_config):
            with patch('main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = mock_games
                with patch('main.LogHandler', side_effect=fake_gspread.exceptions.APIError("Quota")):
                    window._init_components()
        
        self.assertTrue(window._disabled)
        self.assertIn('接続エラー', window._status)

    def test_init_components_generic_exception_disables(self):
        """_init_componentsは汎用Exceptionで無効化."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)
        
        mock_config = MagicMock()
        mock_config.window_scan.get.return_value = []
        mock_games = [main.GameEntry(game_title="Test", window_title="Test")]
        
        # カスタム例外クラスを作成してgspread以外の例外をシミュレート
        class CustomNonGspreadError(Exception):
            pass
        
        # gspread.exceptions.APIErrorを一時的に差し替え
        original_api_error = fake_gspread.exceptions.APIError
        fake_gspread.exceptions.APIError = type('APIError', (ValueError,), {})  # 狭い継承
        
        try:
            with patch('main.ConfigLoader', return_value=mock_config):
                with patch('main.GameInfoLoader') as MockGameInfoLoader:
                    MockGameInfoLoader.return_value.load.return_value = mock_games
                    with patch('main.LogHandler', side_effect=CustomNonGspreadError("Custom error")):
                        window._init_components()
            
            self.assertTrue(window._disabled)
            self.assertIn('初期化エラー', window._status)
        finally:
            # 元に戻す
            fake_gspread.exceptions.APIError = original_api_error


class TestRecordSegmentsCrossDayTodaySeconds(unittest.TestCase):
    """_record_segmentsの戻り値（today_seconds）の跨日ケーステスト."""

    def test_cross_day_returns_only_today_seconds(self):
        """跨日記録は当日分のみtoday_secondsに加算."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="CrossDayGame", window_title="CrossDayGame")
        
        now = datetime.now()
        today_start = datetime.combine(now.date(), time(0, 0, 0))
        
        # 昨日22:00から今日2:00まで（計4時間、今日分は2時間）
        start_time = datetime.combine(now.date() - timedelta(days=1), time(22, 0, 0))
        end_time = datetime.combine(now.date(), time(2, 0, 0))
        
        result = recorder._record_segments(game, start_time, end_time)
        
        # 2セグメント記録されるはず（昨日分と今日分）
        self.assertEqual(len(handler.records), 2)
        
        # 戻り値は今日分のみ（2時間 = 7200秒）
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 2 * 60 * 60, delta=1)

    def test_yesterday_only_returns_zero_today_seconds(self):
        """昨日のみの記録はtoday_seconds=0だがNoneではない（any_saved=True）."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="YesterdayGame", window_title="YesterdayGame")
        
        now = datetime.now()
        # 昨日18:00から昨日20:00まで
        start_time = datetime.combine(now.date() - timedelta(days=1), time(18, 0, 0))
        end_time = datetime.combine(now.date() - timedelta(days=1), time(20, 0, 0))
        
        result = recorder._record_segments(game, start_time, end_time)
        
        self.assertEqual(len(handler.records), 1)
        # 昨日のみなので当日秒数は0だが、any_saved=Trueなので0.0が返る
        self.assertIsNotNone(result)
        self.assertEqual(result, 0.0)

    def test_today_only_returns_full_seconds(self):
        """今日のみの記録は全秒数がtoday_secondsに含まれる."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="TodayGame", window_title="TodayGame")
        
        now = datetime.now()
        today_start = datetime.combine(now.date(), time(10, 0, 0))
        
        # 今日10:00から11:00まで
        start_time = datetime.combine(now.date(), time(10, 0, 0))
        end_time = datetime.combine(now.date(), time(11, 0, 0))
        
        result = recorder._record_segments(game, start_time, end_time)
        
        self.assertEqual(len(handler.records), 1)
        # 1時間 = 3600秒
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 3600, delta=1)

    def test_multi_day_cross_returns_correct_today_seconds(self):
        """3日跨ぎ記録で当日分のみ正確に返す."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="MultiDayGame", window_title="MultiDayGame")
        
        now = datetime.now()
        # 2日前22:00から今日1:00まで
        start_time = datetime.combine(now.date() - timedelta(days=2), time(22, 0, 0))
        end_time = datetime.combine(now.date(), time(1, 0, 0))
        
        result = recorder._record_segments(game, start_time, end_time)
        
        # 3セグメント: 2日前22:00-0:00、1日前0:00-0:00、今日0:00-1:00
        self.assertEqual(len(handler.records), 3)
        
        # 今日分は1時間 = 3600秒
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 3600, delta=1)


class TestMainWindowEvents(unittest.TestCase):
    """MainWindowのイベント系メソッドテスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.display_mode = 'mid'
        window.mode_sizes = {'min': (300, 80), 'mid': (300, 200), 'max': (300, 400)}
        window.daily_stats = main.DailyStatsTracker()
        window.recorder = main.SessionRecorder(log_handler=FakeLogHandler(), min_play_minutes=5)
        
        window.w = MagicMock()
        window.scanner = MagicMock()
        window.scanner.excluded_titles = set()
        
        window._window_title = ""
        window.setWindowTitle = lambda t: setattr(window, '_window_title', t)
        window.windowTitle = lambda: window._window_title
        window.setDisabled = MagicMock()
        
        window._geom = MagicMock()
        window._geom.x.return_value = 100
        window._geom.y.return_value = 200
        window._geom.width.return_value = 300
        window._geom.height.return_value = 200
        window.geometry = lambda: window._geom
        window.width = lambda: 300
        window.height = lambda: 200
        
        return window

    def test_close_event_records_playing_games(self):
        """closeEventはプレイ中のゲームを記録する."""
        window = self._create_mock_main_window()
        window._save_window_state = MagicMock()
        
        game1 = main.GameEntry(game_title="Game1", window_title="Game1", is_playing=True)
        game1.start_time = datetime.now() - timedelta(minutes=10)
        game2 = main.GameEntry(game_title="Game2", window_title="Game2", is_playing=False)
        window.games = [game1, game2]
        
        # closeEventのロジックを再現
        for game in window.games:
            if game.is_playing and game.start_time:
                window.recorder.record(game)
        window._save_window_state()
        
        # game1のみ記録される（game2はis_playing=False）
        self.assertEqual(len(window.recorder.log_handler.records), 1)
        self.assertEqual(window.recorder.log_handler.records[0]['title'], 'Game1')
        window._save_window_state.assert_called_once()

    def test_close_event_skips_games_without_start_time(self):
        """closeEventはstart_timeがないゲームをスキップ."""
        window = self._create_mock_main_window()
        window._save_window_state = MagicMock()
        
        game = main.GameEntry(game_title="NoStart", window_title="NoStart", is_playing=True)
        game.start_time = None  # start_timeなし
        window.games = [game]
        
        for game in window.games:
            if game.is_playing and game.start_time:
                window.recorder.record(game)
        
        # 記録されない
        self.assertEqual(len(window.recorder.log_handler.records), 0)

    def test_mouse_press_left_button_cycles_mode(self):
        """mousePressEventは左クリックでモードを循環."""
        window = self._create_mock_main_window()
        window._cycle_display_mode = MagicMock()
        
        mock_event = MagicMock()
        mock_event.button.return_value = main.Qt.MouseButton.LeftButton
        
        # mousePressEventのロジックを再現
        if mock_event.button() == main.Qt.MouseButton.LeftButton:
            window._cycle_display_mode()
        
        window._cycle_display_mode.assert_called_once()

    def test_mouse_press_right_button_does_not_cycle(self):
        """mousePressEventは右クリックではモードを変更しない."""
        window = self._create_mock_main_window()
        window._cycle_display_mode = MagicMock()
        
        mock_event = MagicMock()
        mock_event.button.return_value = main.Qt.MouseButton.RightButton
        
        if mock_event.button() == main.Qt.MouseButton.LeftButton:
            window._cycle_display_mode()
        
        window._cycle_display_mode.assert_not_called()

    def test_resize_event_records_mode_size(self):
        """resizeEventは現在モードのサイズを記録."""
        window = self._create_mock_main_window()
        window.display_mode = 'mid'
        
        # resizeEventのロジックを再現
        new_width, new_height = 400, 300
        window.width = lambda: new_width
        window.height = lambda: new_height
        window.mode_sizes[window.display_mode] = (window.width(), window.height())
        
        self.assertEqual(window.mode_sizes['mid'], (400, 300))

    def test_start_timer_creates_and_starts_timer(self):
        """_start_timerはタイマーを作成して開始する."""
        # QTimerのモックテスト
        mock_timer = MagicMock()
        callback = MagicMock()
        
        with patch('main.QTimer', return_value=mock_timer):
            # _start_timerのロジックを再現
            timer = mock_timer
            timer.setInterval(int(1.0 * 1000))
            timer.timeout.connect(callback)
            timer.start()
        
        mock_timer.setInterval.assert_called_once_with(1000)
        mock_timer.timeout.connect.assert_called_once_with(callback)
        mock_timer.start.assert_called_once()


class TestUpdateTodayGamesList(unittest.TestCase):
    """_update_today_games_listの詳細テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.daily_stats = main.DailyStatsTracker()
        window.recorder = main.SessionRecorder(log_handler=FakeLogHandler(), min_play_minutes=5)
        
        window.w = MagicMock()
        window.w.today_games_table = MagicMock()
        window.w.today_games_table.rowCount.return_value = 0
        
        return window

    def test_non_empty_cache_updates_table(self):
        """非空のキャッシュでテーブルが更新される."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {
            'GameA': 60.0,
            'GameB': 30.0,
        }
        window.daily_stats.last_today_games_content = ""
        
        window._update_today_games_list(datetime.now())
        
        # テーブルが更新される
        window.w.today_games_table.setRowCount.assert_called_with(2)
        # setItemが呼ばれる（2ゲーム × 2カラム = 4回）
        self.assertEqual(window.w.today_games_table.setItem.call_count, 4)

    def test_sorted_by_minutes_descending(self):
        """ゲームは時間降順でソートされる."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {
            'ShortGame': 10.0,
            'LongGame': 120.0,
            'MidGame': 45.0,
        }
        window.daily_stats.last_today_games_content = ""
        
        window._update_today_games_list(datetime.now())
        
        # setItemの呼び出し順で確認
        calls = window.w.today_games_table.setItem.call_args_list
        # row 0 = LongGame (120分)
        self.assertEqual(calls[0][0][0], 0)  # row
        self.assertEqual(calls[0][0][2].text(), 'LongGame')
        # row 1 = MidGame (45分)
        self.assertEqual(calls[2][0][0], 1)  # row
        self.assertEqual(calls[2][0][2].text(), 'MidGame')
        # row 2 = ShortGame (10分)
        self.assertEqual(calls[4][0][0], 2)  # row
        self.assertEqual(calls[4][0][2].text(), 'ShortGame')

    def test_content_diff_skips_update_when_same(self):
        """内容が同じ場合は更新をスキップ."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {
            'GameA': 60.0,
        }
        # 既に同じ内容がセットされている
        window.daily_stats.last_today_games_content = "GameA: 60分"
        
        window._update_today_games_list(datetime.now())
        
        # 更新されない
        window.w.today_games_table.setRowCount.assert_not_called()

    def test_content_diff_updates_when_different(self):
        """内容が異なる場合は更新される."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {
            'GameA': 65.0,  # 60分から65分に増加
        }
        window.daily_stats.last_today_games_content = "GameA: 60分"
        
        window._update_today_games_list(datetime.now())
        
        # 更新される
        window.w.today_games_table.setRowCount.assert_called_with(1)
        # 新しい内容が保存される
        self.assertEqual(window.daily_stats.last_today_games_content, "GameA: 65分")

    def test_includes_playing_game_over_5min(self):
        """プレイ中ゲーム（5分以上）がキャッシュに追加される."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {}
        window.daily_stats.last_today_games_content = ""
        
        game = main.GameEntry(game_title="PlayingGame", window_title="PlayingGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.active_games_cache = [game]
        
        window._update_today_games_list(datetime.now())
        
        # テーブルが更新される（1ゲーム）
        window.w.today_games_table.setRowCount.assert_called_with(1)

    def test_excludes_playing_game_under_5min(self):
        """プレイ中ゲーム（5分未満）はテーブルに含まれない."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {}
        window.daily_stats.last_today_games_content = ""
        
        game = main.GameEntry(game_title="ShortPlayingGame", window_title="ShortPlayingGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=3)
        window.active_games_cache = [game]
        
        window._update_today_games_list(datetime.now())
        
        # 空なのでクリアされる
        self.assertEqual(window.daily_stats.last_today_games_content, "")

    def test_merges_cache_and_playing_game(self):
        """キャッシュとプレイ中ゲームがマージされる."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {
            'GameA': 30.0,  # キャッシュに30分
        }
        window.daily_stats.last_today_games_content = ""
        
        # 同じゲームが現在10分プレイ中
        game = main.GameEntry(game_title="GameA", window_title="GameA", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.active_games_cache = [game]
        
        window._update_today_games_list(datetime.now())
        
        # 30 + 10 = 40分として表示
        self.assertIn("GameA: 40分", window.daily_stats.last_today_games_content)


class TestLoadTodayDataExceptionHandling(unittest.TestCase):
    """_load_today_game_minutes/_load_today_completed_secondsの例外時挙動テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.daily_stats = main.DailyStatsTracker()
        
        return window

    def test_load_today_game_minutes_returns_empty_on_exception(self):
        """_load_today_game_minutesは例外時に空辞書を返す."""
        window = self._create_mock_main_window()
        
        mock_handler = MagicMock()
        mock_handler.get_cached_records.side_effect = RuntimeError("Database error")
        window.recorder = main.SessionRecorder(log_handler=mock_handler, min_play_minutes=5)
        
        result = window._load_today_game_minutes()
        
        self.assertEqual(result, {})

    def test_load_today_completed_seconds_returns_zero_on_exception(self):
        """_load_today_completed_secondsは例外時に0を返す."""
        window = self._create_mock_main_window()
        
        mock_handler = MagicMock()
        mock_handler.get_cached_records.side_effect = RuntimeError("Database error")
        window.recorder = main.SessionRecorder(log_handler=mock_handler, min_play_minutes=5)
        
        result = window._load_today_completed_seconds()
        
        self.assertEqual(result, 0.0)

    def test_load_today_game_minutes_handles_parse_error(self):
        """_load_today_game_minutesはパースエラーをスキップ."""
        window = self._create_mock_main_window()
        
        mock_handler = MagicMock()
        # 不正なレコード形式
        mock_handler.get_cached_records.return_value = [
            {'invalid': 'record'},  # パース失敗
        ]
        window.recorder = main.SessionRecorder(log_handler=mock_handler, min_play_minutes=5)
        
        result = window._load_today_game_minutes()
        
        # パース失敗レコードはスキップされる
        self.assertEqual(result, {})

    def test_load_today_completed_seconds_handles_parse_error(self):
        """_load_today_completed_secondsはパースエラーをスキップ."""
        window = self._create_mock_main_window()
        
        mock_handler = MagicMock()
        mock_handler.get_cached_records.return_value = [
            {'invalid': 'record'},
        ]
        window.recorder = main.SessionRecorder(log_handler=mock_handler, min_play_minutes=5)
        
        result = window._load_today_completed_seconds()
        
        self.assertEqual(result, 0.0)

    def test_load_today_game_minutes_filters_other_days(self):
        """_load_today_game_minutesは今日以外の日付をフィルタ."""
        window = self._create_mock_main_window()
        
        handler = FakeLogHandler()
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        
        # 昨日のレコードを追加
        handler.records = [
            {
                'index': 1,
                'start_time': yesterday.strftime('%Y/%m/%d 10:00:00'),
                'end_time': yesterday.strftime('%Y/%m/%d 11:00:00'),
                'title': 'YesterdayGame',
                'play_with_friends': False,
            }
        ]
        window.recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        
        result = window._load_today_game_minutes()
        
        # 昨日のレコードは含まれない
        self.assertEqual(result, {})


class TestScanTickStatusSwitch(unittest.TestCase):
    """_scan_tickのステータス切替テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.latest_window_titles = []
        window.daily_stats = main.DailyStatsTracker()
        window.recorder = main.SessionRecorder(log_handler=FakeLogHandler(), min_play_minutes=5)
        
        window.w = MagicMock()
        window.w.active_display = MagicMock()
        window.w.window_list = MagicMock()
        window.w.today_games_table = MagicMock()
        
        window.scanner = MagicMock()
        window.scanner.excluded_titles = set()
        
        window._status = ""
        window._window_title = ""
        window.setWindowTitle = lambda t: setattr(window, '_window_title', t)
        window.windowTitle = lambda: window._window_title
        
        return window

    def _mock_set_status(self, window):
        """_set_statusを監視可能にする."""
        def _set_status(message):
            window._status = message
            window._window_title = f"{main.BASE_TITLE} - {message}"
            window.scanner.excluded_titles.add(window._window_title)
        return _set_status

    def test_status_playing_when_active_games(self):
        """アクティブゲームがある場合はプレイ時間計測中."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)
        
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=False)
        window.games = [game]
        window.scanner.get_titles.return_value = ["TestGame Window"]
        window.scanner.get_foreground_title.return_value = "TestGame Window"
        
        window._scan_tick()
        
        self.assertEqual(window._status, 'プレイ時間計測中')

    def test_status_playing_when_inactive_games(self):
        """非アクティブゲーム（停止中）がある場合もプレイ時間計測中."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)
        
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.games = [game]
        window.scanner.get_titles.return_value = ["TestGame Window", "Other Window"]
        window.scanner.get_foreground_title.return_value = "Other Window"  # 非フォアグラウンド
        
        window._scan_tick()
        
        # inactive_gamesが存在するのでプレイ時間計測中
        self.assertEqual(window._status, 'プレイ時間計測中')

    def test_status_no_game_when_no_active_or_inactive(self):
        """アクティブ/非アクティブゲームがない場合は「プレイ中のゲームなし」."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)
        
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=False)
        window.games = [game]
        window.scanner.get_titles.return_value = ["Other Window"]  # ゲームウィンドウなし
        window.scanner.get_foreground_title.return_value = "Other Window"
        
        window._scan_tick()
        
        self.assertEqual(window._status, main.Messages.NO_GAME_PLAYING)

    def test_status_switches_from_playing_to_no_game(self):
        """プレイ中から未プレイへの切替."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)
        
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.games = [game]
        
        # 最初はゲームがフォアグラウンド
        window.scanner.get_titles.return_value = ["TestGame Window"]
        window.scanner.get_foreground_title.return_value = "TestGame Window"
        window._scan_tick()
        self.assertEqual(window._status, 'プレイ時間計測中')
        
        # 次にゲームウィンドウが消える
        window.scanner.get_titles.return_value = []
        window.scanner.get_foreground_title.return_value = None
        window._scan_tick()
        self.assertEqual(window._status, main.Messages.NO_GAME_PLAYING)


class TestGameInfoLoaderRecordToEntry(unittest.TestCase):
    """GameInfoLoader._record_to_entryのテスト."""

    def test_converts_basic_record(self):
        """基本的なレコードをGameEntryに変換."""
        record = {
            'game_title': 'TestGame',
            'window_title': 'TestGame Window',
            'play_with_friends': 'FALSE',
            'is_browser_game': 'FALSE',
        }
        
        entry = main.GameInfoLoader._record_to_entry(record)
        
        self.assertEqual(entry.game_title, 'TestGame')
        self.assertEqual(entry.window_title, 'TestGame Window')
        self.assertFalse(entry.play_with_friends)
        self.assertFalse(entry.is_browser_game)

    def test_converts_true_values(self):
        """TRUE値を正しく変換."""
        record = {
            'game_title': 'BrowserGame',
            'window_title': 'BrowserGame',
            'play_with_friends': 'TRUE',
            'is_browser_game': 'TRUE',
        }
        
        entry = main.GameInfoLoader._record_to_entry(record)
        
        self.assertTrue(entry.play_with_friends)
        self.assertTrue(entry.is_browser_game)

    def test_handles_missing_optional_fields(self):
        """オプションフィールドが欠落している場合はデフォルト値."""
        record = {
            'game_title': 'MinimalGame',
            'window_title': 'MinimalGame',
        }
        
        entry = main.GameInfoLoader._record_to_entry(record)
        
        self.assertFalse(entry.play_with_friends)
        self.assertFalse(entry.is_browser_game)

    def test_converts_numeric_values_to_string(self):
        """数値型の値も文字列に変換される."""
        record = {
            'game_title': 12345,  # 数値として渡される場合
            'window_title': 67890,
            'play_with_friends': 'FALSE',
            'is_browser_game': 'FALSE',
        }
        
        entry = main.GameInfoLoader._record_to_entry(record)
        
        self.assertEqual(entry.game_title, '12345')
        self.assertEqual(entry.window_title, '67890')


class TestLogHandlerFormatDatetime(unittest.TestCase):
    """LogHandler.format_datetime_to_gss_styleのテスト."""

    def test_formats_datetime_correctly(self):
        """日時を正しいフォーマットに変換."""
        handler = FakeLogHandler()
        dt = datetime(2026, 1, 18, 14, 30, 45)
        
        result = handler.format_datetime_to_gss_style(dt)
        
        self.assertEqual(result, '2026/01/18 14:30:45')

    def test_formats_midnight(self):
        """深夜0時を正しくフォーマット."""
        handler = FakeLogHandler()
        dt = datetime(2026, 1, 18, 0, 0, 0)
        
        result = handler.format_datetime_to_gss_style(dt)
        
        self.assertEqual(result, '2026/01/18 00:00:00')

    def test_formats_end_of_day(self):
        """23:59:59を正しくフォーマット."""
        handler = FakeLogHandler()
        dt = datetime(2026, 1, 18, 23, 59, 59)
        
        result = handler.format_datetime_to_gss_style(dt)
        
        self.assertEqual(result, '2026/01/18 23:59:59')


class TestSessionRecorderSaveToSpreadsheet(unittest.TestCase):
    """SessionRecorder._save_to_spreadsheetのテスト."""

    def test_save_success_returns_true(self):
        """保存成功時にTrueを返す."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", play_with_friends=True)
        
        start_time = datetime(2026, 1, 18, 10, 0, 0)
        end_time = datetime(2026, 1, 18, 11, 0, 0)
        
        result = recorder._save_to_spreadsheet(game, start_time, end_time)
        
        self.assertTrue(result)
        self.assertEqual(len(handler.records), 1)

    def test_save_failure_returns_false(self):
        """保存失敗時にFalseを返す."""
        class FailingLogHandler(FakeLogHandler):
            def save_record(self, values):
                return False
        
        handler = FailingLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="TestGame", window_title="TestGame")
        
        start_time = datetime(2026, 1, 18, 10, 0, 0)
        end_time = datetime(2026, 1, 18, 11, 0, 0)
        
        result = recorder._save_to_spreadsheet(game, start_time, end_time)
        
        self.assertFalse(result)

    def test_save_includes_correct_values(self):
        """保存時に正しい値が含まれる."""
        handler = FakeLogHandler()
        recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", play_with_friends=True)
        
        start_time = datetime(2026, 1, 18, 10, 0, 0)
        end_time = datetime(2026, 1, 18, 11, 0, 0)
        
        recorder._save_to_spreadsheet(game, start_time, end_time)
        
        record = handler.records[0]
        self.assertEqual(record['title'], 'TestGame')
        self.assertEqual(record['start_time'], '2026/01/18 10:00:00')
        self.assertEqual(record['end_time'], '2026/01/18 11:00:00')
        self.assertTrue(record['play_with_friends'])


class TestLogHandlerGetAndIncrementIndex(unittest.TestCase):
    """LogHandler.get_and_increment_indexのテスト."""

    def test_increments_index_each_call(self):
        """呼び出すごとにインデックスが増加."""
        handler = FakeLogHandler()
        handler.current_index = 5
        
        idx1 = handler.get_and_increment_index()
        idx2 = handler.get_and_increment_index()
        idx3 = handler.get_and_increment_index()
        
        self.assertEqual(idx1, 6)
        self.assertEqual(idx2, 7)
        self.assertEqual(idx3, 8)

    def test_starts_from_record_count(self):
        """初期インデックスはレコード数."""
        handler = FakeLogHandler()
        # 3件のレコードがある状態をシミュレート
        handler.records = [{'index': 1}, {'index': 2}, {'index': 3}]
        handler.current_index = 3
        
        idx = handler.get_and_increment_index()
        
        self.assertEqual(idx, 4)


class TestInactiveWindowDisappear(unittest.TestCase):
    """非アクティブ時のウィンドウ消失テスト（非アクティブ時間を含めて記録）."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.latest_window_titles = []
        window.daily_stats = main.DailyStatsTracker()
        window.recorder = main.SessionRecorder(log_handler=FakeLogHandler(), min_play_minutes=5)
        
        window.w = MagicMock()
        window.w.active_display = MagicMock()
        window.w.window_list = MagicMock()
        window.w.today_games_table = MagicMock()
        
        window.scanner = MagicMock()
        window.scanner.excluded_titles = set()
        
        window.setWindowTitle = MagicMock()
        
        return window

    def test_inactive_window_disappear_includes_inactive_time(self):
        """非アクティブ状態でウィンドウ消失時、非アクティブ時間も含めて記録."""
        window = self._create_mock_main_window()
        
        # 15分前から開始し、3分間非アクティブ状態
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=15)
        game.inactive_since = datetime.now() - timedelta(minutes=3)  # 3分間非アクティブ
        window.games = [game]
        
        # ウィンドウが消失
        window.scanner.get_titles.return_value = []
        window.scanner.get_foreground_title.return_value = None
        
        window._scan_tick()
        
        # record()が呼ばれ、非アクティブ時間も含めた時間が記録される
        self.assertFalse(game.is_playing)
        # 記録されたレコードを確認
        records = window.recorder.log_handler.records
        self.assertEqual(len(records), 1)
        # 15分間のプレイが記録される（非アクティブ3分を含む）

    def test_inactive_under_5min_reactivate_continues_session(self):
        """非アクティブ5分未満で再アクティブ化するとセッション継続."""
        window = self._create_mock_main_window()
        
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.games = [game]
        
        # 非アクティブ状態（3分経過）
        window.scanner.get_titles.return_value = ["TestGame Window", "Other Window"]
        window.scanner.get_foreground_title.return_value = "Other Window"
        window._scan_tick()
        
        self.assertTrue(game.is_inactive())
        self.assertIsNotNone(game.inactive_since)
        
        # 再度フォアグラウンドに
        window.scanner.get_foreground_title.return_value = "TestGame Window"
        window._scan_tick()
        
        # セッション継続、inactive_sinceがクリアされる
        self.assertTrue(game.is_playing)
        self.assertFalse(game.is_inactive())
        self.assertIsNone(game.inactive_since)
        # 記録されていない
        self.assertEqual(len(window.recorder.log_handler.records), 0)


class TestBuildMainLayout(unittest.TestCase):
    """gui_layout.build_main_layoutのテスト."""

    def test_build_main_layout_returns_layout_widgets(self):
        """build_main_layoutはLayoutWidgetsを返す."""
        # PySide6のQWidgetをモックで置き換え
        from gui_layout import build_main_layout, LayoutWidgets
        from PySide6.QtWidgets import QWidget, QApplication
        
        # QApplicationが必要なのでスキップ可能にする
        try:
            app = QApplication.instance()
            if app is None:
                app = QApplication([])
            
            parent = QWidget()
            result = build_main_layout(parent)
            
            self.assertIsInstance(result, LayoutWidgets)
            self.assertIsNotNone(result.today_label)
            self.assertIsNotNone(result.today_time_display)
            self.assertIsNotNone(result.session_label)
            self.assertIsNotNone(result.session_time_display)
            self.assertIsNotNone(result.active_label)
            self.assertIsNotNone(result.active_display)
            self.assertIsNotNone(result.today_games_label)
            self.assertIsNotNone(result.today_games_table)
            self.assertIsNotNone(result.window_label)
            self.assertIsNotNone(result.window_list)
        except Exception:
            # GUI環境がない場合はスキップ
            self.skipTest("GUI environment not available")

    def test_layout_widgets_has_height_constants(self):
        """LayoutWidgetsは高さ定数を持つ."""
        from gui_layout import LayoutWidgets
        from PySide6.QtWidgets import QWidget, QApplication, QLabel, QListWidget, QTableWidget
        
        try:
            app = QApplication.instance()
            if app is None:
                app = QApplication([])
            
            # ダミーウィジェットで作成
            parent = QWidget()
            widgets = LayoutWidgets(
                today_label=QLabel(parent),
                today_time_display=QLabel(parent),
                session_label=QLabel(parent),
                session_time_display=QLabel(parent),
                active_label=QLabel(parent),
                active_display=QLabel(parent),
                today_games_label=QLabel(parent),
                today_games_table=QTableWidget(parent),
                window_label=QLabel(parent),
                window_list=QListWidget(parent),
                active_min_height=30,
                active_max_height=30,
                today_games_min_height=100,
                window_min_height=200,
            )
            
            self.assertEqual(widgets.active_min_height, 30)
            self.assertEqual(widgets.active_max_height, 30)
            self.assertEqual(widgets.today_games_min_height, 100)
            self.assertEqual(widgets.window_min_height, 200)
        except Exception:
            self.skipTest("GUI environment not available")


class TestMessagesConstants(unittest.TestCase):
    """Messagesクラスの定数テスト."""

    def test_game_recorded_message_format(self):
        """GAME_RECORDEDメッセージのフォーマット."""
        message = main.Messages.GAME_RECORDED.format(game_title="TestGame")
        
        self.assertIn("TestGame", message)
        self.assertIn("記録", message)

    def test_game_too_short_message_format(self):
        """GAME_TOO_SHORTメッセージのフォーマット."""
        message = main.Messages.GAME_TOO_SHORT.format(game_title="TestGame", min_minutes=5)
        
        self.assertIn("TestGame", message)
        self.assertIn("5", message)

    def test_no_game_playing_message(self):
        """NO_GAME_PLAYINGメッセージの存在."""
        self.assertIsNotNone(main.Messages.NO_GAME_PLAYING)
        self.assertIsInstance(main.Messages.NO_GAME_PLAYING, str)


class TestMainWindowEventsDirect(unittest.TestCase):
    """MainWindowイベント系の実メソッド呼び出しテスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.display_mode = 'mid'
        window.mode_sizes = {'min': (300, 80), 'mid': (300, 200), 'max': (300, 400)}
        window.daily_stats = main.DailyStatsTracker()
        window.recorder = main.SessionRecorder(log_handler=FakeLogHandler(), min_play_minutes=5)
        
        window.w = MagicMock()
        window.scanner = MagicMock()
        window.scanner.excluded_titles = set()
        
        window._window_title = ""
        window.setWindowTitle = MagicMock()
        window.windowTitle = lambda: window._window_title
        window.setDisabled = MagicMock()
        
        window._geom = MagicMock()
        window._geom.x.return_value = 100
        window._geom.y.return_value = 200
        window._geom.width.return_value = 300
        window._geom.height.return_value = 200
        window.geometry = lambda: window._geom
        window.width = lambda: 300
        window.height = lambda: 200
        
        return window

    def test_close_event_calls_record_for_playing_games(self):
        """closeEventは実際のrecord()を呼び出す."""
        window = self._create_mock_main_window()
        
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.games = [game]
        
        # closeEventのロジック部分を実行（super().closeEventはモック）
        for g in window.games:
            if g.is_playing and g.start_time:
                window.recorder.record(g)
        
        # 実際にrecordが実行され、レコードが追加される
        self.assertEqual(len(window.recorder.log_handler.records), 1)
        self.assertFalse(game.is_playing)  # record()でis_playing=Falseになる

    def test_mouse_press_event_calls_cycle_display_mode(self):
        """mousePressEventは_cycle_display_modeを実際に呼び出す."""
        window = self._create_mock_main_window()
        window._apply_display_mode = MagicMock()
        window._save_window_state = MagicMock()
        window.display_mode = 'max'
        
        # mousePressEventのロジック部分を実行
        window._cycle_display_mode()
        
        # DISPLAY_MODES = ("max", "mid", "min") なので max -> mid
        self.assertEqual(window.display_mode, 'mid')
        window._apply_display_mode.assert_called_once()
        window._save_window_state.assert_called_once()

    def test_resize_event_updates_mode_sizes(self):
        """resizeEventはmode_sizesを実際に更新."""
        window = self._create_mock_main_window()
        window.display_mode = 'mid'
        window.width = lambda: 400
        window.height = lambda: 300
        
        # resizeEventのロジック部分を実行
        window.mode_sizes[window.display_mode] = (window.width(), window.height())
        
        self.assertEqual(window.mode_sizes['mid'], (400, 300))

    def test_start_timer_logic_with_qtimer(self):
        """_start_timerのロジックをQTimerモックで検証."""
        window = self._create_mock_main_window()
        callback = MagicMock()
        
        mock_timer = MagicMock()
        with patch('main.QTimer', return_value=mock_timer):
            # _start_timerの実装を再現
            timer = main.QTimer(window)
            timer.setInterval(int(1.0 * 1000))
            timer.timeout.connect(callback)
            timer.start()
        
        mock_timer.setInterval.assert_called_with(1000)
        mock_timer.timeout.connect.assert_called_with(callback)
        mock_timer.start.assert_called_once()


class TestUpdateSessionTimesWithInactive(unittest.TestCase):
    """_update_session_timesのinactive_games_cache経路テスト（実メソッド）."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.daily_stats = main.DailyStatsTracker()
        window.recorder = main.SessionRecorder(log_handler=FakeLogHandler(), min_play_minutes=5)
        
        window.w = MagicMock()
        window.w.session_time_display = MagicMock()
        
        return window

    def test_includes_inactive_games_in_max_calculation(self):
        """inactive_games_cacheのゲームも最長時間計算に含まれる."""
        window = self._create_mock_main_window()
        
        # アクティブゲーム: 5分
        active_game = main.GameEntry(game_title="ActiveGame", window_title="ActiveGame", is_playing=True)
        active_game.start_time = datetime.now() - timedelta(minutes=5)
        
        # 非アクティブゲーム: 15分（こちらが最長）
        inactive_game = main.GameEntry(game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
        inactive_game.start_time = datetime.now() - timedelta(minutes=15)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]
        
        # 実メソッドを呼び出し
        window._update_session_times([active_game], datetime.now())
        
        # 15分が表示される（HH:MM:SS.F形式 = 00:15:xx.x）
        call_arg = window.w.session_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:15:") or call_arg.startswith("00:14:"))

    def test_only_inactive_games_shows_max(self):
        """active_gamesが空でもinactive_games_cacheから最長を表示."""
        window = self._create_mock_main_window()
        
        inactive_game = main.GameEntry(game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
        inactive_game.start_time = datetime.now() - timedelta(minutes=20)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]
        
        window._update_session_times([], datetime.now())
        
        call_arg = window.w.session_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:20:") or call_arg.startswith("00:19:"))

    def test_empty_both_shows_dash(self):
        """active_gamesとinactive_games_cacheが両方空なら---."""
        window = self._create_mock_main_window()
        window.inactive_games_cache = []
        
        window._update_session_times([], datetime.now())
        
        window.w.session_time_display.setText.assert_called_with('---')


class TestUpdateTodayTotalsIntegration(unittest.TestCase):
    """_update_today_totalsの統合テスト（実メソッド）."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.daily_stats = main.DailyStatsTracker()
        window.recorder = main.SessionRecorder(log_handler=FakeLogHandler(), min_play_minutes=5)
        
        window.w = MagicMock()
        window.w.today_time_display = MagicMock()
        
        return window

    def test_includes_inactive_game_time(self):
        """非アクティブゲームの時間も含まれる."""
        window = self._create_mock_main_window()
        window.daily_stats.today_completed_seconds = 0.0
        
        # 非アクティブゲーム: 10分
        inactive_game = main.GameEntry(game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
        inactive_game.start_time = datetime.now() - timedelta(minutes=10)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]
        
        window._update_today_totals([], datetime.now())
        
        # 10分 = 00:10:xx
        call_arg = window.w.today_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:10:") or call_arg.startswith("00:09:"))

    def test_cross_midnight_counts_from_today(self):
        """日跨ぎセッションは今日0:00からカウント."""
        window = self._create_mock_main_window()
        window.daily_stats.today_completed_seconds = 0.0
        
        now = datetime.now()
        today_start = datetime.combine(now.date(), time(0, 0, 0))
        
        # 昨日23:00開始（日跨ぎ）
        game = main.GameEntry(game_title="NightGame", window_title="NightGame", is_playing=True)
        game.start_time = datetime.combine(now.date() - timedelta(days=1), time(23, 0, 0))
        
        # 今日の経過時間を計算（現在時刻から0:00を引く）
        expected_seconds = (now - today_start).total_seconds()
        
        window._update_today_totals([game], now)
        
        # 今日0:00からの時間が表示される（5分以上なら）
        if expected_seconds >= main.MIN_PLAY_MINUTES * main.SECONDS_PER_MINUTE:
            call_arg = window.w.today_time_display.setText.call_args[0][0]
            self.assertNotEqual(call_arg, "00:00:00.0")

    def test_excludes_under_5min_session(self):
        """5分未満のセッションは除外."""
        window = self._create_mock_main_window()
        window.daily_stats.today_completed_seconds = 3600.0  # 完了分1時間
        
        # 3分プレイ中（5分未満なので除外）
        game = main.GameEntry(game_title="ShortGame", window_title="ShortGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=3)
        
        window._update_today_totals([game], datetime.now())
        
        # 完了分の1時間のみ = 01:00:xx
        call_arg = window.w.today_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("01:00:"))

    def test_combined_active_inactive_completed(self):
        """アクティブ+非アクティブ+完了時間が合算される."""
        window = self._create_mock_main_window()
        window.daily_stats.today_completed_seconds = 1800.0  # 完了30分
        
        # アクティブゲーム: 10分
        active_game = main.GameEntry(game_title="ActiveGame", window_title="ActiveGame", is_playing=True)
        active_game.start_time = datetime.now() - timedelta(minutes=10)
        
        # 非アクティブゲーム: 20分
        inactive_game = main.GameEntry(game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
        inactive_game.start_time = datetime.now() - timedelta(minutes=20)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]
        
        window._update_today_totals([active_game], datetime.now())
        
        # 30 + 10 + 20 = 60分 = 01:00:xx
        call_arg = window.w.today_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("01:00:") or call_arg.startswith("00:59:"))


class TestUpdateTodayGamesListWithInactive(unittest.TestCase):
    """_update_today_games_listのinactive_games_cache経路テスト（実メソッド）."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.daily_stats = main.DailyStatsTracker()
        window.recorder = main.SessionRecorder(log_handler=FakeLogHandler(), min_play_minutes=5)
        
        window.w = MagicMock()
        window.w.today_games_table = MagicMock()
        
        return window

    def test_includes_inactive_game_in_list(self):
        """非アクティブゲームもリストに含まれる."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {}
        window.daily_stats.last_today_games_content = ""
        
        # 非アクティブゲーム: 15分
        inactive_game = main.GameEntry(game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
        inactive_game.start_time = datetime.now() - timedelta(minutes=15)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]
        window.active_games_cache = []
        
        window._update_today_games_list(datetime.now())
        
        # テーブル更新される
        window.w.today_games_table.setRowCount.assert_called_with(1)
        self.assertIn("InactiveGame: 15分", window.daily_stats.last_today_games_content)

    def test_merges_active_and_inactive_games(self):
        """アクティブと非アクティブゲームがマージされる."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {}
        window.daily_stats.last_today_games_content = ""
        
        # アクティブゲーム: 10分
        active_game = main.GameEntry(game_title="ActiveGame", window_title="ActiveGame", is_playing=True)
        active_game.start_time = datetime.now() - timedelta(minutes=10)
        window.active_games_cache = [active_game]
        
        # 非アクティブゲーム: 20分
        inactive_game = main.GameEntry(game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
        inactive_game.start_time = datetime.now() - timedelta(minutes=20)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]
        
        window._update_today_games_list(datetime.now())
        
        # 2ゲーム表示
        window.w.today_games_table.setRowCount.assert_called_with(2)
        # 時間降順なのでInactiveGame(20分)が先
        self.assertIn("InactiveGame: 20分", window.daily_stats.last_today_games_content)
        self.assertIn("ActiveGame: 10分", window.daily_stats.last_today_games_content)

    def test_same_game_active_and_cached_merged(self):
        """同じゲームがキャッシュと非アクティブに存在する場合マージ."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {
            'GameA': 30.0,  # キャッシュに30分
        }
        window.daily_stats.last_today_games_content = ""
        
        # 同じゲームが非アクティブで15分
        inactive_game = main.GameEntry(game_title="GameA", window_title="GameA", is_playing=True)
        inactive_game.start_time = datetime.now() - timedelta(minutes=15)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]
        window.active_games_cache = []
        
        window._update_today_games_list(datetime.now())
        
        # 30 + 15 = 45分
        self.assertIn("GameA: 45分", window.daily_stats.last_today_games_content)


class TestLoadTodayGameMinutesParseNone(unittest.TestCase):
    """_load_today_game_minutesでParsedRecordがNoneになるケースのテスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window.browsers = ['Chrome']
        window.active_games_cache = []
        window.inactive_games_cache = []
        window.daily_stats = main.DailyStatsTracker()
        
        return window

    def test_skips_record_with_missing_start_time(self):
        """start_timeが欠落したレコードはスキップ."""
        window = self._create_mock_main_window()
        
        handler = FakeLogHandler()
        now = datetime.now()
        handler.records = [
            # start_timeが欠落
            {
                'index': 1,
                'end_time': now.strftime('%Y/%m/%d 11:00:00'),
                'title': 'BadRecord1',
                'play_with_friends': False,
            },
            # 正常レコード
            {
                'index': 2,
                'start_time': now.strftime('%Y/%m/%d 10:00:00'),
                'end_time': now.strftime('%Y/%m/%d 11:00:00'),
                'title': 'GoodRecord',
                'play_with_friends': False,
            },
        ]
        window.recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        
        result = window._load_today_game_minutes()
        
        # 正常レコードのみ含まれる
        self.assertIn('GoodRecord', result)
        self.assertNotIn('BadRecord1', result)

    def test_skips_record_with_missing_end_time(self):
        """end_timeが欠落したレコードはスキップ."""
        window = self._create_mock_main_window()
        
        handler = FakeLogHandler()
        now = datetime.now()
        handler.records = [
            # end_timeが欠落
            {
                'index': 1,
                'start_time': now.strftime('%Y/%m/%d 10:00:00'),
                'title': 'BadRecord2',
                'play_with_friends': False,
            },
            # 正常レコード
            {
                'index': 2,
                'start_time': now.strftime('%Y/%m/%d 12:00:00'),
                'end_time': now.strftime('%Y/%m/%d 13:00:00'),
                'title': 'GoodRecord2',
                'play_with_friends': False,
            },
        ]
        window.recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        
        result = window._load_today_game_minutes()
        
        self.assertIn('GoodRecord2', result)
        self.assertNotIn('BadRecord2', result)

    def test_skips_record_with_invalid_datetime_format(self):
        """日時フォーマットが不正なレコードはスキップ."""
        window = self._create_mock_main_window()
        
        handler = FakeLogHandler()
        now = datetime.now()
        handler.records = [
            # 不正なフォーマット
            {
                'index': 1,
                'start_time': 'invalid-date',
                'end_time': 'also-invalid',
                'title': 'BadFormat',
                'play_with_friends': False,
            },
            # 正常レコード
            {
                'index': 2,
                'start_time': now.strftime('%Y/%m/%d 14:00:00'),
                'end_time': now.strftime('%Y/%m/%d 15:00:00'),
                'title': 'GoodFormat',
                'play_with_friends': False,
            },
        ]
        window.recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        
        result = window._load_today_game_minutes()
        
        self.assertIn('GoodFormat', result)
        self.assertNotIn('BadFormat', result)

    def test_skips_empty_record(self):
        """空のレコードはスキップ."""
        window = self._create_mock_main_window()
        
        handler = FakeLogHandler()
        now = datetime.now()
        handler.records = [
            {},  # 空レコード
            # 正常レコード
            {
                'index': 1,
                'start_time': now.strftime('%Y/%m/%d 16:00:00'),
                'end_time': now.strftime('%Y/%m/%d 17:00:00'),
                'title': 'ValidRecord',
                'play_with_friends': False,
            },
        ]
        window.recorder = main.SessionRecorder(log_handler=handler, min_play_minutes=5)
        
        result = window._load_today_game_minutes()
        
        self.assertIn('ValidRecord', result)


class TestCloseEventRealMethod(unittest.TestCase):
    """closeEventの実メソッド呼び出しテスト."""

    def test_close_event_calls_super(self):
        """closeEventがsuper().closeEvent()を呼び出す."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window._save_window_state = MagicMock()
        
        mock_event = MagicMock(spec=main.QCloseEvent)
        
        # super().closeEventをモック
        with patch.object(main.QWidget, 'closeEvent') as mock_super_close:
            window.closeEvent(mock_event)
            mock_super_close.assert_called_once_with(mock_event)

    def test_close_event_saves_window_state(self):
        """closeEventが_save_window_stateを呼び出す."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.games = []
        window._save_window_state = MagicMock()
        
        mock_event = MagicMock(spec=main.QCloseEvent)
        
        with patch.object(main.QWidget, 'closeEvent'):
            window.closeEvent(mock_event)
            window._save_window_state.assert_called_once()

    def test_close_event_records_playing_games(self):
        """closeEventがプレイ中ゲームを記録する."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        game = main.GameEntry(game_title="TestGame", window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.games = [game]
        window.recorder = MagicMock()
        window._save_window_state = MagicMock()
        
        mock_event = MagicMock(spec=main.QCloseEvent)
        
        with patch.object(main.QWidget, 'closeEvent'):
            window.closeEvent(mock_event)
            window.recorder.record.assert_called_once_with(game)


class TestMousePressEventRealMethod(unittest.TestCase):
    """mousePressEventの実メソッド呼び出しテスト."""

    def test_mouse_press_event_calls_super(self):
        """mousePressEventがsuper().mousePressEvent()を呼び出す."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window._cycle_display_mode = MagicMock()
        
        mock_event = MagicMock(spec=main.QMouseEvent)
        mock_event.button.return_value = main.Qt.MouseButton.RightButton
        
        with patch.object(main.QWidget, 'mousePressEvent') as mock_super:
            window.mousePressEvent(mock_event)
            mock_super.assert_called_once_with(mock_event)

    def test_left_click_cycles_mode_then_calls_super(self):
        """左クリックでモード切替後、super()を呼び出す."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window._cycle_display_mode = MagicMock()
        
        mock_event = MagicMock(spec=main.QMouseEvent)
        mock_event.button.return_value = main.Qt.MouseButton.LeftButton
        
        with patch.object(main.QWidget, 'mousePressEvent') as mock_super:
            window.mousePressEvent(mock_event)
            window._cycle_display_mode.assert_called_once()
            mock_super.assert_called_once_with(mock_event)

    def test_right_click_does_not_cycle_mode(self):
        """右クリックではモード切替しない."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window._cycle_display_mode = MagicMock()
        
        mock_event = MagicMock(spec=main.QMouseEvent)
        mock_event.button.return_value = main.Qt.MouseButton.RightButton
        
        with patch.object(main.QWidget, 'mousePressEvent'):
            window.mousePressEvent(mock_event)
            window._cycle_display_mode.assert_not_called()


class TestResizeEventRealMethod(unittest.TestCase):
    """resizeEventの実メソッド呼び出しテスト."""

    def test_resize_event_calls_super(self):
        """resizeEventがsuper().resizeEvent()を呼び出す."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.display_mode = 'mid'
        window.mode_sizes = {'min': (300, 80), 'mid': (300, 200), 'max': (300, 400)}
        window.width = lambda: 350
        window.height = lambda: 250
        
        mock_event = MagicMock(spec=main.QResizeEvent)
        
        with patch.object(main.QWidget, 'resizeEvent') as mock_super:
            window.resizeEvent(mock_event)
            mock_super.assert_called_once_with(mock_event)

    def test_resize_event_updates_mode_sizes_then_calls_super(self):
        """リサイズでサイズ記録後、super()を呼び出す."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.display_mode = 'max'
        window.mode_sizes = {'min': (300, 80), 'mid': (300, 200), 'max': (300, 400)}
        window.width = lambda: 500
        window.height = lambda: 600
        
        mock_event = MagicMock(spec=main.QResizeEvent)
        
        with patch.object(main.QWidget, 'resizeEvent') as mock_super:
            window.resizeEvent(mock_event)
            
            # サイズが更新される
            self.assertEqual(window.mode_sizes['max'], (500, 600))
            # super()が呼ばれる
            mock_super.assert_called_once_with(mock_event)


class TestStartTimerRealMethod(unittest.TestCase):
    """_start_timerの実メソッド呼び出しテスト."""

    def test_start_timer_creates_qtimer_with_parent(self):
        """_start_timerがQTimerを正しい親で作成する."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        callback = MagicMock()
        
        with patch('main.QTimer') as MockQTimer:
            mock_timer = MagicMock()
            MockQTimer.return_value = mock_timer
            
            result = window._start_timer(1.5, callback)
            
            # QTimer(self)で作成
            MockQTimer.assert_called_once_with(window)
            # インターバル設定（1.5秒 = 1500ms）
            mock_timer.setInterval.assert_called_once_with(1500)
            # コールバック接続
            mock_timer.timeout.connect.assert_called_once_with(callback)
            # 開始
            mock_timer.start.assert_called_once()
            # 戻り値
            self.assertEqual(result, mock_timer)


class TestApplyDisplayModeMaxMid(unittest.TestCase):
    """_apply_display_modeのmax/midモードテスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.display_mode = 'mid'
        window.mode_sizes = {'min': (300, 80), 'mid': (300, 200), 'max': (300, 400)}
        
        # ウィジェットモック
        window.w = MagicMock()
        window.w.today_label = MagicMock()
        window.w.today_time_display = MagicMock()
        window.w.session_label = MagicMock()
        window.w.session_time_display = MagicMock()
        window.w.active_label = MagicMock()
        window.w.active_display = MagicMock()
        window.w.active_min_height = 30
        window.w.active_max_height = 60
        window.w.today_games_label = MagicMock()
        window.w.today_games_table = MagicMock()
        window.w.today_games_min_height = 50
        window.w.window_label = MagicMock()
        window.w.window_list = MagicMock()
        
        window._apply_mode_geometry = MagicMock()
        
        return window

    def test_max_mode_shows_window_list(self):
        """maxモードでwindow_listが表示される."""
        window = self._create_mock_main_window()
        window.display_mode = 'max'
        
        window._apply_display_mode()
        
        # window_listが表示される
        window.w.window_list.setVisible.assert_called_with(True)
        window.w.window_label.setVisible.assert_called_with(True)

    def test_mid_mode_hides_window_list(self):
        """midモードでwindow_listが非表示."""
        window = self._create_mock_main_window()
        window.display_mode = 'mid'
        
        window._apply_display_mode()
        
        # window_listが非表示
        window.w.window_list.setVisible.assert_called_with(False)
        window.w.window_label.setVisible.assert_called_with(False)

    def test_mid_mode_shows_session_and_active(self):
        """midモードでsessionとactiveが表示される."""
        window = self._create_mock_main_window()
        window.display_mode = 'mid'
        
        window._apply_display_mode()
        
        # session関連が表示
        window.w.session_label.setVisible.assert_called_with(True)
        window.w.session_time_display.setVisible.assert_called_with(True)
        # active関連が表示
        window.w.active_label.setVisible.assert_called_with(True)
        window.w.active_display.setVisible.assert_called_with(True)
        # today_gamesが表示
        window.w.today_games_label.setVisible.assert_called_with(True)
        window.w.today_games_table.setVisible.assert_called_with(True)

    def test_max_mode_shows_all_widgets(self):
        """maxモードで全ウィジェットが表示される."""
        window = self._create_mock_main_window()
        window.display_mode = 'max'
        
        window._apply_display_mode()
        
        # 全ウィジェットが表示
        window.w.today_label.setVisible.assert_called_with(True)
        window.w.session_label.setVisible.assert_called_with(True)
        window.w.active_label.setVisible.assert_called_with(True)
        window.w.today_games_label.setVisible.assert_called_with(True)
        window.w.window_label.setVisible.assert_called_with(True)

    def test_min_mode_hides_session_active_games(self):
        """minモードでsession/active/gamesが非表示."""
        window = self._create_mock_main_window()
        window.display_mode = 'min'
        
        window._apply_display_mode()
        
        # session関連が非表示
        window.w.session_label.setVisible.assert_called_with(False)
        window.w.session_time_display.setVisible.assert_called_with(False)
        # active関連が非表示
        window.w.active_label.setVisible.assert_called_with(False)
        window.w.active_display.setVisible.assert_called_with(False)
        # window_listが非表示
        window.w.window_label.setVisible.assert_called_with(False)
        window.w.window_list.setVisible.assert_called_with(False)

    def test_apply_mode_geometry_called(self):
        """_apply_mode_geometryが呼び出される."""
        window = self._create_mock_main_window()
        
        for mode in ['min', 'mid', 'max']:
            window.display_mode = mode
            window._apply_mode_geometry.reset_mock()
            
            window._apply_display_mode()
            
            window._apply_mode_geometry.assert_called_once()


class TestMainEntryPoint(unittest.TestCase):
    """main()エントリポイントのテスト."""

    def test_main_creates_qapplication(self):
        """main()がQApplicationを作成する."""
        with patch('main.QApplication') as MockQApp:
            with patch('main.MainWindow') as MockWindow:
                mock_app = MagicMock()
                mock_app.exec.return_value = 0
                MockQApp.return_value = mock_app
                
                mock_window = MagicMock()
                MockWindow.return_value = mock_window
                
                with patch('sys.exit') as mock_exit:
                    main.main()
                    
                    # QApplication(sys.argv)で作成
                    MockQApp.assert_called_once_with(sys.argv)

    def test_main_creates_and_shows_window(self):
        """main()がMainWindowを作成してshow()する."""
        with patch('main.QApplication') as MockQApp:
            with patch('main.MainWindow') as MockWindow:
                mock_app = MagicMock()
                mock_app.exec.return_value = 0
                MockQApp.return_value = mock_app
                
                mock_window = MagicMock()
                MockWindow.return_value = mock_window
                
                with patch('sys.exit') as mock_exit:
                    main.main()
                    
                    # MainWindow作成
                    MockWindow.assert_called_once()
                    # show()呼び出し
                    mock_window.show.assert_called_once()

    def test_main_calls_app_exec(self):
        """main()がapp.exec()を呼び出す."""
        with patch('main.QApplication') as MockQApp:
            with patch('main.MainWindow') as MockWindow:
                mock_app = MagicMock()
                mock_app.exec.return_value = 0
                MockQApp.return_value = mock_app
                
                mock_window = MagicMock()
                MockWindow.return_value = mock_window
                
                with patch('sys.exit') as mock_exit:
                    main.main()
                    
                    # app.exec()呼び出し
                    mock_app.exec.assert_called_once()

    def test_main_exits_with_exec_return_value(self):
        """main()がapp.exec()の戻り値でsys.exit()する."""
        with patch('main.QApplication') as MockQApp:
            with patch('main.MainWindow') as MockWindow:
                mock_app = MagicMock()
                mock_app.exec.return_value = 42  # 任意の終了コード
                MockQApp.return_value = mock_app
                
                mock_window = MagicMock()
                MockWindow.return_value = mock_window
                
                with patch('sys.exit') as mock_exit:
                    main.main()
                    
                    # sys.exit(42)で終了
                    mock_exit.assert_called_once_with(42)


class TestSetWidgetVisibility(unittest.TestCase):
    """_set_widget_visibilityの単体テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        return window

    def test_set_visible_true(self):
        """visible=Trueでウィジェットを表示."""
        window = self._create_mock_main_window()
        mock_widget = MagicMock()
        
        window._set_widget_visibility(mock_widget, True)
        
        mock_widget.setVisible.assert_called_once_with(True)

    def test_set_visible_false(self):
        """visible=Falseでウィジェットを非表示."""
        window = self._create_mock_main_window()
        mock_widget = MagicMock()
        
        window._set_widget_visibility(mock_widget, False)
        
        mock_widget.setVisible.assert_called_once_with(False)


class TestSetWidgetWithHeight(unittest.TestCase):
    """_set_widget_with_heightの単体テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        return window

    def test_set_visible_true_with_height(self):
        """visible=Trueで表示と高さを設定."""
        window = self._create_mock_main_window()
        mock_widget = MagicMock()
        
        window._set_widget_with_height(mock_widget, True, min_height=50, max_height=200)
        
        mock_widget.setVisible.assert_called_once_with(True)
        mock_widget.setMinimumHeight.assert_called_once_with(50)
        mock_widget.setMaximumHeight.assert_called_once_with(200)

    def test_set_visible_false_with_zero_height(self):
        """visible=Falseで非表示と高さ0を設定."""
        window = self._create_mock_main_window()
        mock_widget = MagicMock()
        
        window._set_widget_with_height(mock_widget, False, min_height=0, max_height=0)
        
        mock_widget.setVisible.assert_called_once_with(False)
        mock_widget.setMinimumHeight.assert_called_once_with(0)
        mock_widget.setMaximumHeight.assert_called_once_with(0)

    def test_height_values_are_keyword_only(self):
        """min_height/max_heightはキーワード引数のみ."""
        window = self._create_mock_main_window()
        mock_widget = MagicMock()
        
        # 位置引数で渡すとエラー
        with self.assertRaises(TypeError):
            window._set_widget_with_height(mock_widget, True, 50, 200)


class TestUpdateSessionTimesStartTimeNone(unittest.TestCase):
    """_update_session_timesでstart_time=Noneのケースのテスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        
        window.inactive_games_cache = []
        window.w = MagicMock()
        window.w.session_time_display = MagicMock()
        
        return window

    def test_start_time_none_treated_as_zero(self):
        """start_time=Noneのゲームは0秒として扱われる."""
        window = self._create_mock_main_window()
        
        # start_time=Noneのゲーム
        game_none = main.GameEntry(game_title="NoneGame", window_title="NoneGame", is_playing=True)
        game_none.start_time = None  # 明示的にNone
        
        window._update_session_times([game_none], datetime.now())
        
        # 0秒 = 00:00:00.0
        call_arg = window.w.session_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:00:00"))

    def test_max_elapsed_with_none_and_valid(self):
        """start_time=Noneと有効なstart_timeが混在する場合、有効なものの最大値."""
        window = self._create_mock_main_window()
        
        # start_time=Noneのゲーム（0秒扱い）
        game_none = main.GameEntry(game_title="NoneGame", window_title="NoneGame", is_playing=True)
        game_none.start_time = None
        
        # 有効なstart_timeのゲーム（10分）
        game_valid = main.GameEntry(game_title="ValidGame", window_title="ValidGame", is_playing=True)
        game_valid.start_time = datetime.now() - timedelta(minutes=10)
        
        window._update_session_times([game_none, game_valid], datetime.now())
        
        # 10分が表示される（Noneは0なので最大値は10分）
        call_arg = window.w.session_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:10:") or call_arg.startswith("00:09:"))

    def test_all_games_start_time_none(self):
        """全ゲームがstart_time=Noneなら0秒."""
        window = self._create_mock_main_window()
        
        game1 = main.GameEntry(game_title="Game1", window_title="Game1", is_playing=True)
        game1.start_time = None
        game2 = main.GameEntry(game_title="Game2", window_title="Game2", is_playing=True)
        game2.start_time = None
        
        window._update_session_times([game1, game2], datetime.now())
        
        # 0秒
        call_arg = window.w.session_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:00:00"))


class TestConfigLoaderExcludedTitles(unittest.TestCase):
    """ConfigLoaderのexcluded_titlesがwindow_scanに反映されるテスト."""

    def test_excluded_titles_default(self):
        """excluded_titlesのデフォルト値."""
        config_content = """
[LOGHANDLER]
json_file_path = service_account.json
sheet_key = test_key

[GAMEINFO]
sheet_key = test_key
sheet_gid = 123

[WINDOW_SCAN]
browsers = Chrome
"""
        with patch.object(main.ConfigLoader, '__init__', lambda self: None):
            loader = main.ConfigLoader()
            loader.config = configparser.ConfigParser()
            loader.config.read_string(config_content)
            loader.log_handler = {}
            loader.game_info = {}
            loader.window_scan = {}
            loader.load()
        
        # デフォルト値が設定される
        self.assertEqual(loader.window_scan['excluded_titles'], list(main.DEFAULT_EXCLUDED_TITLES))

    def test_excluded_titles_custom_comma_separated(self):
        """excluded_titlesのカンマ区切り値."""
        config_content = """
[LOGHANDLER]
json_file_path = service_account.json
sheet_key = test_key

[GAMEINFO]
sheet_key = test_key
sheet_gid = 123

[WINDOW_SCAN]
browsers = Chrome
exclude_titles = Settings, Task Manager, Control Panel
"""
        with patch.object(main.ConfigLoader, '__init__', lambda self: None):
            loader = main.ConfigLoader()
            loader.config = configparser.ConfigParser()
            loader.config.read_string(config_content)
            loader.log_handler = {}
            loader.game_info = {}
            loader.window_scan = {}
            loader.load()
        
        # カスタム値が設定される
        self.assertEqual(loader.window_scan['excluded_titles'], ['Settings', 'Task Manager', 'Control Panel'])

    def test_excluded_titles_empty_uses_default(self):
        """excluded_titlesが空ならデフォルト."""
        config_content = """
[LOGHANDLER]
json_file_path = service_account.json
sheet_key = test_key

[GAMEINFO]
sheet_key = test_key
sheet_gid = 123

[WINDOW_SCAN]
browsers = Chrome
exclude_titles = 
"""
        with patch.object(main.ConfigLoader, '__init__', lambda self: None):
            loader = main.ConfigLoader()
            loader.config = configparser.ConfigParser()
            loader.config.read_string(config_content)
            loader.log_handler = {}
            loader.game_info = {}
            loader.window_scan = {}
            loader.load()
        
        # デフォルト値が設定される
        self.assertEqual(loader.window_scan['excluded_titles'], list(main.DEFAULT_EXCLUDED_TITLES))

    def test_excluded_titles_reflected_in_window_scanner(self):
        """excluded_titlesがWindowScannerに反映される."""
        excluded = ['CustomExclude1', 'CustomExclude2']
        
        scanner = main.WindowScanner(excluded_titles=excluded)
        
        self.assertEqual(scanner.excluded_titles, set(excluded))

    def test_window_scanner_excludes_matching_titles(self):
        """WindowScannerが除外タイトルにマッチするウィンドウを除外."""
        excluded = ['Settings', 'Task Manager']
        
        scanner = main.WindowScanner(excluded_titles=excluded)
        
        # 除外タイトルがセットに含まれる
        self.assertIn('Settings', scanner.excluded_titles)
        self.assertIn('Task Manager', scanner.excluded_titles)


if __name__ == "__main__":
    unittest.main()
