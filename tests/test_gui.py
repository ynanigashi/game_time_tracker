"""GUIモジュールのテスト（PySide6を必要としないユニットテスト）."""

import unittest
from datetime import date

# 共通スタブをインストール（他モジュール import 前に実行）
from tests.test_stubs import install_stubs
install_stubs()

# Now import the gui module
from src.core.services import DailyStatsTracker
from src.core.time_utils import format_hms


class TestDailyStatsTracker(unittest.TestCase):
    """DailyStatsTrackerのテスト."""

    def test_initial_state(self):
        """初期状態の確認."""
        tracker = DailyStatsTracker()
        self.assertEqual(tracker.today_completed_seconds, 0.0)
        self.assertEqual(tracker.today_game_minutes_cache, {})
        self.assertEqual(tracker.last_today_games_content, "")

    def test_no_day_change_returns_false(self):
        """日付が変わっていない場合はFalseを返す."""
        current_date = date(2026, 1, 18)
        tracker = DailyStatsTracker(get_current_date=lambda: current_date)
        
        # 同日なのでFalse
        result = tracker.check_day_change()
        self.assertFalse(result)
        self.assertEqual(tracker.today_completed_seconds, 0.0)

    def test_day_change_resets_stats(self):
        """日付が変わったら統計がリセットされる."""
        # 1/18から開始
        dates = [date(2026, 1, 18)]
        tracker = DailyStatsTracker(get_current_date=lambda: dates[0])
        
        # データを追加
        tracker.today_completed_seconds = 3600.0  # 1時間
        tracker.today_game_minutes_cache = {"GameA": 60.0}
        tracker.last_today_games_content = "GameA: 60分"
        
        # 日付を1/19に変更
        dates[0] = date(2026, 1, 19)
        
        # check_day_changeを呼ぶとリセットされる
        result = tracker.check_day_change()
        
        self.assertTrue(result)
        self.assertEqual(tracker.today_completed_seconds, 0.0)
        self.assertEqual(tracker.today_game_minutes_cache, {})
        self.assertEqual(tracker.last_today_games_content, "")

    def test_day_change_updates_last_checked_date(self):
        """日付変更後、_last_checked_dateが更新される."""
        dates = [date(2026, 1, 18)]
        tracker = DailyStatsTracker(get_current_date=lambda: dates[0])
        
        # 日付を変更
        dates[0] = date(2026, 1, 19)
        tracker.check_day_change()
        
        # 再度呼んでもFalse（既に同日）
        result = tracker.check_day_change()
        self.assertFalse(result)

    def test_add_completed_seconds(self):
        """add_completed_secondsで時間が加算される."""
        tracker = DailyStatsTracker()
        tracker.add_completed_seconds(1800.0)  # 30分
        self.assertEqual(tracker.today_completed_seconds, 1800.0)
        
        tracker.add_completed_seconds(900.0)  # 15分追加
        self.assertEqual(tracker.today_completed_seconds, 2700.0)

    def test_update_game_minutes_cache(self):
        """update_game_minutes_cacheでキャッシュが更新される."""
        tracker = DailyStatsTracker()
        new_cache = {"GameA": 30.0, "GameB": 45.0}
        tracker.update_game_minutes_cache(new_cache)
        self.assertEqual(tracker.today_game_minutes_cache, new_cache)

    def test_multiple_day_changes(self):
        """複数回の日付変更でも正しくリセットされる."""
        dates = [date(2026, 1, 18)]
        tracker = DailyStatsTracker(get_current_date=lambda: dates[0])
        
        # 1日目のデータ
        tracker.add_completed_seconds(3600.0)
        
        # 2日目に変更
        dates[0] = date(2026, 1, 19)
        tracker.check_day_change()
        self.assertEqual(tracker.today_completed_seconds, 0.0)
        
        # 2日目のデータ
        tracker.add_completed_seconds(1800.0)
        self.assertEqual(tracker.today_completed_seconds, 1800.0)
        
        # 3日目に変更
        dates[0] = date(2026, 1, 20)
        tracker.check_day_change()
        self.assertEqual(tracker.today_completed_seconds, 0.0)


class TestFormatHms(unittest.TestCase):
    """format_hms関数のテスト."""

    def test_zero_seconds(self):
        """0秒の場合."""
        self.assertEqual(format_hms(0), "00:00:00.0")

    def test_seconds_only(self):
        """秒のみ."""
        self.assertEqual(format_hms(45.5), "00:00:45.5")

    def test_minutes_and_seconds(self):
        """分と秒."""
        self.assertEqual(format_hms(125.0), "00:02:05.0")

    def test_hours_minutes_seconds(self):
        """時間・分・秒."""
        self.assertEqual(format_hms(3725.0), "01:02:05.0")


if __name__ == "__main__":
    unittest.main()

