# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""time_utils.py のユニットテスト."""

import unittest
from datetime import datetime, time, timedelta

# 共通スタブをインストール
from tests.test_stubs import install_stubs
install_stubs()

from src.core import time_utils
from src.core.time_utils import format_hms, split_by_day, calc_today_elapsed_seconds, GSS_DATETIME_FORMAT

from src.core import models
from src.core import services
from tests.test_stubs import FakeLogHandler


class TestSplitByDay(unittest.TestCase):
    """日を跨いだセッション分割のテスト."""

    def setUp(self):
        handler = FakeLogHandler()
        self.recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)

    def test_same_day_no_split(self):
        """同日内のセッションは分割されない."""
        start = datetime(2026, 1, 10, 22, 0, 0)
        end = datetime(2026, 1, 10, 23, 30, 0)
        segments = time_utils.split_by_day(start, end)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0], (start, end))

    def test_cross_midnight_splits_into_two(self):
        """日を跨ぐセッションは2つに分割される."""
        start = datetime(2026, 1, 10, 23, 30, 0)
        end = datetime(2026, 1, 11, 1, 30, 0)
        segments = time_utils.split_by_day(start, end)
        self.assertEqual(len(segments), 2)
        # 1日目: 23:30 - 翌日00:00 (半開区間)
        self.assertEqual(segments[0][0], start)
        self.assertEqual(segments[0][1], datetime(2026, 1, 11, 0, 0, 0))
        # 2日目: 00:00 - 01:30
        self.assertEqual(segments[1][0], datetime(2026, 1, 11, 0, 0, 0))
        self.assertEqual(segments[1][1], end)

    def test_cross_two_days_splits_into_three(self):
        """2日を跨ぐセッションは3つに分割される."""
        start = datetime(2026, 1, 10, 23, 0, 0)
        end = datetime(2026, 1, 12, 2, 0, 0)
        segments = time_utils.split_by_day(start, end)
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
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(
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


class TestGSSDatetimeFormat(unittest.TestCase):
    """GSS_DATETIME_FORMAT定数のテスト."""

    def test_format_constant_matches_expected(self):
        """GSS_DATETIME_FORMATが期待する形式と一致する."""
        self.assertEqual(time_utils.GSS_DATETIME_FORMAT, "%Y/%m/%d %H:%M:%S")

    def test_parse_with_format_constant(self):
        """GSS_DATETIME_FORMATでパースできる."""
        time_str = "2026/01/18 14:30:45"
        parsed = datetime.strptime(time_str, time_utils.GSS_DATETIME_FORMAT)
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 1)
        self.assertEqual(parsed.day, 18)
        self.assertEqual(parsed.hour, 14)
        self.assertEqual(parsed.minute, 30)
        self.assertEqual(parsed.second, 45)


class TestFormatHms(unittest.TestCase):
    """_format_hms()のテスト."""

    def test_zero_seconds(self):
        """0秒のフォーマット."""
        self.assertEqual(time_utils.format_hms(0), "00:00:00.0")

    def test_seconds_only(self):
        """秒のみのフォーマット."""
        # 浮動小数点はint()で切り捨てられる: 45.3 * 10 = 453 -> 45.3
        self.assertEqual(time_utils.format_hms(45.35), "00:00:45.3")

    def test_minutes_and_seconds(self):
        """分と秒のフォーマット."""
        self.assertEqual(time_utils.format_hms(125.5), "00:02:05.5")

    def test_hours_minutes_seconds(self):
        """時間・分・秒のフォーマット."""
        # 1時間1分1.7秒 = 3661.7秒だが、int()で切り捨てられるので.75で.7になる
        self.assertEqual(time_utils.format_hms(3661.75), "01:01:01.7")

    def test_large_hours(self):
        """長時間のフォーマット."""
        # 10時間30分45.2秒
        self.assertEqual(time_utils.format_hms(37845.25), "10:30:45.2")


class TestSplitByDayBoundaryConditions(unittest.TestCase):
    """_split_by_day()の境界条件テスト."""

    def setUp(self):
        handler = FakeLogHandler()
        self.recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)

    def test_end_at_exactly_midnight(self):
        """0:00ちょうどに終了した場合の境界テスト."""
        start = datetime(2026, 1, 10, 23, 30, 0)
        end = datetime(2026, 1, 11, 0, 0, 0)
        segments = time_utils.split_by_day(start, end)
        
        # 半開区間により2セグメントに分割されるが、2つ目は空区間
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0][0], start)
        self.assertEqual(segments[0][1], datetime(2026, 1, 11, 0, 0, 0))
        self.assertEqual(segments[1][0], datetime(2026, 1, 11, 0, 0, 0))
        self.assertEqual(segments[1][1], end)

    def test_start_at_exactly_midnight(self):
        """0:00ちょうどに開始した場合."""
        start = datetime(2026, 1, 11, 0, 0, 0)
        end = datetime(2026, 1, 11, 1, 0, 0)
        segments = time_utils.split_by_day(start, end)
        
        # 分割なし
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0], (start, end))

    def test_segment_under_min_play_minutes_not_recorded(self):
        """5分未満のセグメントは記録されない."""
        handler = FakeLogHandler()
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(
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


class TestTimeUtilsCalcTodayElapsedSeconds(unittest.TestCase):
    """time_utils.calc_today_elapsed_seconds()の境界テスト."""

    def test_same_day_full_duration(self):
        """同じ日の場合、全経過時間を返す."""
        from src.core.time_utils import calc_today_elapsed_seconds
        
        start = datetime(2025, 1, 15, 10, 0, 0)
        now = datetime(2025, 1, 15, 12, 30, 0)
        
        result = calc_today_elapsed_seconds(start, now)
        
        expected = 2.5 * 3600  # 2.5時間
        self.assertEqual(result, expected)

    def test_cross_midnight_only_today(self):
        """日跨ぎの場合、今日の0:00からの経過時間のみを返す."""
        from src.core.time_utils import calc_today_elapsed_seconds
        
        start = datetime(2025, 1, 14, 23, 0, 0)  # 昨日23時
        now = datetime(2025, 1, 15, 2, 0, 0)     # 今日2時
        
        result = calc_today_elapsed_seconds(start, now)
        
        expected = 2 * 3600  # 今日の0:00から2時間
        self.assertEqual(result, expected)

    def test_exactly_midnight_start(self):
        """ちょうど0:00開始の場合."""
        from src.core.time_utils import calc_today_elapsed_seconds
        
        start = datetime(2025, 1, 15, 0, 0, 0)
        now = datetime(2025, 1, 15, 1, 30, 0)
        
        result = calc_today_elapsed_seconds(start, now)
        
        expected = 1.5 * 3600
        self.assertEqual(result, expected)

    def test_multiple_days_ago(self):
        """複数日前からの場合、今日の経過時間のみ."""
        from src.core.time_utils import calc_today_elapsed_seconds
        
        start = datetime(2025, 1, 13, 10, 0, 0)  # 2日前
        now = datetime(2025, 1, 15, 3, 0, 0)     # 今日3時
        
        result = calc_today_elapsed_seconds(start, now)
        
        expected = 3 * 3600  # 今日の0:00から3時間
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()

