"""GUIモジュールのテスト（PySide6を必要としないユニットテスト）."""

import sys
import types
import unittest
from datetime import date
from typing import Any

# Stub external dependencies before importing gui module
# SimpleNamespaceを使って動的属性追加の型エラーを回避
fake_pyside6_core: Any = types.SimpleNamespace(
    QTimer=type("QTimer", (), {}),
    Qt=types.SimpleNamespace(
        MouseButton=types.SimpleNamespace(LeftButton=1)
    ),
)

fake_pyside6_gui: Any = types.SimpleNamespace(
    QCloseEvent=type("QCloseEvent", (), {}),
    QMouseEvent=type("QMouseEvent", (), {}),
    QResizeEvent=type("QResizeEvent", (), {}),
)

fake_pyside6_widgets: Any = types.SimpleNamespace(
    QApplication=type("QApplication", (), {}),
    QWidget=type("QWidget", (), {}),
    QTableWidgetItem=type("QTableWidgetItem", (), {}),
    QLabel=type("QLabel", (), {}),
    QListWidget=type("QListWidget", (), {}),
    QVBoxLayout=type("QVBoxLayout", (), {}),
    QHBoxLayout=type("QHBoxLayout", (), {}),
    QTableWidget=type("QTableWidget", (), {}),
    QHeaderView=type("QHeaderView", (), {}),
)

fake_gspread: Any = types.SimpleNamespace(
    service_account=lambda filename=None: None,
    exceptions=types.SimpleNamespace(APIError=Exception),
)
fake_pygetwindow: Any = types.SimpleNamespace(getAllWindows=lambda: [])

sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
sys.modules.setdefault("PySide6.QtCore", types.ModuleType("PySide6.QtCore"))
sys.modules.setdefault("PySide6.QtGui", types.ModuleType("PySide6.QtGui"))
sys.modules.setdefault("PySide6.QtWidgets", types.ModuleType("PySide6.QtWidgets"))
sys.modules.setdefault("gspread", types.ModuleType("gspread"))
sys.modules.setdefault("pygetwindow", types.ModuleType("pygetwindow"))

# ModuleTypeに属性を設定
for attr, val in vars(fake_pyside6_core).items():
    setattr(sys.modules["PySide6.QtCore"], attr, val)
for attr, val in vars(fake_pyside6_gui).items():
    setattr(sys.modules["PySide6.QtGui"], attr, val)
for attr, val in vars(fake_pyside6_widgets).items():
    setattr(sys.modules["PySide6.QtWidgets"], attr, val)
for attr, val in vars(fake_gspread).items():
    setattr(sys.modules["gspread"], attr, val)
for attr, val in vars(fake_pygetwindow).items():
    setattr(sys.modules["pygetwindow"], attr, val)

# Now import the gui module
from gui import DailyStatsTracker, _format_hms


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
    """_format_hms関数のテスト."""

    def test_zero_seconds(self):
        """0秒の場合."""
        self.assertEqual(_format_hms(0), "00:00:00.0")

    def test_seconds_only(self):
        """秒のみ."""
        self.assertEqual(_format_hms(45.5), "00:00:45.5")

    def test_minutes_and_seconds(self):
        """分と秒."""
        self.assertEqual(_format_hms(125.0), "00:02:05.0")

    def test_hours_minutes_seconds(self):
        """時間・分・秒."""
        self.assertEqual(_format_hms(3725.0), "01:02:05.0")


if __name__ == "__main__":
    unittest.main()
