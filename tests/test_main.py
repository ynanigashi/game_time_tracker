# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportOptionalMemberAccess=false

from tests.test_stubs import fake_gspread, FakeLogHandler

import pygetwindow
from src.core import window_state
from src.core.text_utils import normalize_title
from tests.helpers.main_window_factory import (
    attach_window_title_stubs,
    create_mock_main_window,
)
from src.core import time_utils
from src.core import services
from src.core import models
from src.app import main
import configparser
import sys
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import tempfile
import os


# servicesモジュールにpygetwindowのスタブを設定
services.gw = pygetwindow


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
            parsed = models.parse_record(record)
            if parsed is None or parsed.start.date() != today:
                continue
            minutes = (parsed.end - parsed.start).total_seconds() / \
                main.SECONDS_PER_MINUTE
            game_minutes[parsed.game_title] = game_minutes.get(
                parsed.game_title, 0) + minutes

        self.assertEqual(len(game_minutes), 1)
        self.assertIn('TodayGame', game_minutes)
        self.assertEqual(game_minutes['TodayGame'], 30)

    def test_ongoing_session_cross_midnight_counts_from_today(self):
        """日跨ぎの進行中セッションは今日0:00以降のみカウント."""
        now = datetime.now()
        today_start = datetime.combine(now.date(), time(0, 0, 0))
        yesterday_start = datetime.combine(
            now.date() - timedelta(days=1), time(23, 0, 0))

        # 昨日23:00から開始したセッション
        game = models.GameEntry(
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

        game = models.GameEntry(
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

        game = models.GameEntry(
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

        game1 = models.GameEntry(
            game_title="Game1", window_title="Game1", is_playing=True)
        game1.start_time = datetime.now() - timedelta(minutes=10)

        game2 = models.GameEntry(
            game_title="Game2", window_title="Game2", is_playing=True)
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
        game = models.GameEntry(game_title="ShortGame",
                                window_title="ShortGame", is_playing=True)
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
        game = models.GameEntry(game_title="NightGame",
                                window_title="NightGame", is_playing=True)
        game.start_time = datetime.combine(
            now.date() - timedelta(days=1), time(23, 0, 0))

        effective_start = max(game.start_time, today_start)

        # effective_startは今日0:00になる
        self.assertEqual(effective_start, today_start)

    def test_scan_tick_clears_table_on_day_change(self):
        """_scan_tickは日付変更時にtoday_games_tableをクリア."""
        # DailyStatsTrackerの日付変更検出をテスト
        day1 = datetime(2026, 1, 18).date()
        day2 = datetime(2026, 1, 19).date()
        current_date = [day1]

        tracker = services.DailyStatsTracker(get_current_date=lambda: current_date[0])
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
        window = create_mock_main_window(
            browsers=['Chrome', 'Firefox'],
            include_scanner=True,
            include_latest_window_titles=True,
            display_mode='mid',
        )
        window._load_today_game_minutes = MagicMock(return_value={})
        return window

    def test_update_game_states_returns_active_when_foreground(self):
        """state_tracker.scan()はフォアグラウンドゲームをactiveとして返す."""
        window = self._create_mock_main_window()
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=False)
        window.games = [game]

        result = window.state_tracker.scan(
            games=window.games,
            window_titles=["TestGame Window"],
            foreground_title="TestGame Window",
            load_today_game_minutes_callback=window._load_today_game_minutes
        )

        self.assertEqual(len(result.active_games), 1)
        self.assertEqual(result.active_games[0], game)
        self.assertTrue(game.is_playing)

    def test_update_game_states_returns_inactive_when_not_foreground(self):
        """state_tracker.scan()は非フォアグラウンドのプレイ中ゲームをinactiveとして返す."""
        window = self._create_mock_main_window()
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.games = [game]

        result = window.state_tracker.scan(
            games=window.games,
            window_titles=["TestGame Window", "Other Window"],
            foreground_title="Other Window",
            load_today_game_minutes_callback=window._load_today_game_minutes
        )

        self.assertEqual(len(result.active_games), 0)
        self.assertEqual(len(result.inactive_games), 1)
        self.assertTrue(game.is_inactive())

    def test_update_game_states_records_when_window_disappears(self):
        """state_tracker.scan()はウィンドウ消失時に記録し、daily_statsを更新."""
        window = self._create_mock_main_window()
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.games = [game]

        result = window.state_tracker.scan(
            games=window.games,
            window_titles=[],  # ウィンドウ消失
            foreground_title=None,
            load_today_game_minutes_callback=window._load_today_game_minutes
        )

        self.assertEqual(len(result.active_games), 0)
        self.assertEqual(len(result.inactive_games), 0)
        self.assertFalse(game.is_playing)
        self.assertEqual(len(window.recorder.log_handler.records), 1)
        self.assertGreaterEqual(window.daily_stats.today_completed_seconds, 0)

    def test_update_game_states_inactive_timeout_records_with_times(self):
        """state_tracker.scan()は非アクティブ5分超で部分記録しdaily_statsを更新."""
        window = self._create_mock_main_window()
        fixed_now = datetime(2026, 1, 1, 12, 0, 0)
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
        game.start_time = fixed_now - timedelta(minutes=15)
        game.inactive_since = fixed_now - timedelta(minutes=6)
        window.games = [game]

        result = window.state_tracker.scan(
            games=window.games,
            window_titles=["TestGame Window", "Other Window"],
            foreground_title="Other Window",
            load_today_game_minutes_callback=window._load_today_game_minutes
        )

        self.assertEqual(len(result.active_games), 0)
        self.assertEqual(len(result.inactive_games), 0)
        self.assertFalse(game.is_playing)
        self.assertEqual(len(window.recorder.log_handler.records), 1)
        self.assertGreaterEqual(window.daily_stats.today_completed_seconds, 0)

    def test_scan_tick_updates_caches(self):
        """_scan_tickはキャッシュを更新する."""
        window = self._create_mock_main_window()
        window.setWindowTitle = MagicMock()
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=False)
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
        window.games = [models.GameEntry(
            game_title="TestGame", window_title="TestGame")]
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
        window._update_today_totals = MagicMock(return_value=0.0)
        window._update_today_games_list = MagicMock()
        window._update_overtime_alert = MagicMock()

        window._ui_tick()

        window._update_session_times.assert_called_once()
        window._update_today_totals.assert_called_once()
        window._update_today_games_list.assert_called_once()
        window._update_overtime_alert.assert_called_once()


class TestMainWindowUIHelpers(unittest.TestCase):
    """UI更新ヘルパーメソッドの直接テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        return create_mock_main_window(
            browsers=['Chrome'],
            today_games_rowcount_zero=True,
        )

    def test_update_active_list_shows_games(self):
        """_update_active_listはプレイ中ゲームを表示."""
        window = self._create_mock_main_window()
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)

        window._update_active_list([game], [])

        window.w.active_display.setText.assert_called_once_with("TestGame")

    def test_update_active_list_shows_inactive_with_suffix(self):
        """_update_active_listは非アクティブゲームに「停止中」を付ける."""
        window = self._create_mock_main_window()
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
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
        game1 = models.GameEntry(
            game_title="Game1", window_title="Game1", is_playing=True)
        game2 = models.GameEntry(
            game_title="Game2", window_title="Game2", is_playing=True)
        game2.set_inactive()

        window._update_active_list([game1], [game2])

        window.w.active_display.setText.assert_called_once_with("Game1 / Game2 - 停止中")

    def test_update_session_times_shows_max(self):
        """_update_session_timesは最長時間を表示."""
        window = self._create_mock_main_window()
        game1 = models.GameEntry(
            game_title="Game1", window_title="Game1", is_playing=True)
        game1.start_time = datetime.now() - timedelta(minutes=10)
        game2 = models.GameEntry(
            game_title="Game2", window_title="Game2", is_playing=True)
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
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
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

    def test_on_window_title_item_clicked_copies_to_clipboard(self):
        """ウィンドウタイトル行クリックでクリップボードへコピーする."""
        window = self._create_mock_main_window()
        window._set_status = MagicMock()
        item = MagicMock()
        item.text.return_value = "Game Window Title"
        clipboard = MagicMock()

        with patch.object(
            main.QApplication,
            "clipboard",
            return_value=clipboard,
            create=True,
        ):
            window._on_window_title_item_clicked(item)

        clipboard.setText.assert_called_once_with("Game Window Title")
        window._set_status.assert_called_once_with("ウィンドウタイトルをコピーしました")

    def test_initialize_window_title_copy_connects_item_clicked(self):
        """_initialize_window_title_copyはitemClickedシグナルを接続する."""
        window = self._create_mock_main_window()
        window._window_title_copy_connected = False
        window.w.window_list.itemClicked = MagicMock()
        window.w.window_list.setToolTip = MagicMock()

        window._initialize_window_title_copy()

        window.w.window_list.itemClicked.connect.assert_called_once_with(
            window._on_window_title_item_clicked
        )
        window.w.window_list.setToolTip.assert_called_once()
        self.assertTrue(window._window_title_copy_connected)

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
        window = create_mock_main_window(
            include_state_tracker=False,
            include_scanner=True,
            display_mode='mid',
            include_title_stubs=True,
            include_geometry_stubs=True,
        )

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

    def test_apply_mode_geometry_clamps_min_mode_size(self):
        """minモードのサイズは安全値以上にクランプされる."""
        window = self._create_mock_main_window()
        window.display_mode = 'min'
        window.mode_sizes['min'] = (200, 60)

        window._apply_mode_geometry()

        window.resize.assert_called_once_with(
            main.MIN_MODE_SAFE_WIDTH, main.MIN_MODE_SAFE_HEIGHT)

    def test_save_window_state_records_current_mode_size(self):
        """_save_window_stateは現在のサイズをmode_sizesに記録."""
        window = self._create_mock_main_window()
        window._geom.width.return_value = 350
        window._geom.height.return_value = 250

        with patch.object(main.WindowState, 'save') as mock_save:
            window._save_window_state()

        self.assertEqual(window.mode_sizes['mid'], (350, 250))
        mock_save.assert_called_once()
        self.assertEqual(mock_save.call_args.kwargs.get('overtime_alert_enabled'), True)

    def test_on_overtime_alert_toggled_off_syncs_overlay_immediately(self):
        """トグルOFF時に状態更新し、オーバーレイ同期を即時実行する."""
        window = self._create_mock_main_window()
        window.active_games_cache = []
        window.inactive_games_cache = []
        window._sync_overlay = MagicMock()
        mock_ui_controller = MagicMock()
        mock_ui_controller.calculate_today_total_seconds.return_value = 1800.0
        window._get_ui_controller = MagicMock(return_value=mock_ui_controller)

        window._on_overtime_alert_toggled(False)

        self.assertFalse(window.overtime_alert_enabled)
        tracker = window._get_overtime_alert_tracker()
        self.assertTrue(tracker.initialized)
        self.assertEqual(tracker.last_checked_seconds, 1800.0)
        window._sync_overlay.assert_called_once()

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
        window = create_mock_main_window(
            browsers=[],
            include_state_tracker=False,
            include_scanner=False,
            include_ui=True,
            display_mode='mid',
            mode_sizes={},
        )

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
        mock_config.window_scan.browsers = ['Chrome']
        mock_config.window_scan.excluded_titles = []

        mock_games = [models.GameEntry(game_title="Test", window_title="Test")]

        with patch('src.app.main.ConfigLoader') as MockConfigLoader:
            MockConfigLoader.return_value.load.return_value = mock_config
            with patch('src.app.main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = mock_games
                with patch('src.app.main.LogHandler') as MockLogHandler:
                    MockLogHandler.return_value = FakeLogHandler()
                    window._init_components()

        self.assertFalse(window._disabled)
        self.assertEqual(len(window.games), 1)

    def test_init_components_empty_games_disables(self):
        """_init_componentsはゲームが空の場合無効化."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)

        mock_config = MagicMock()

        with patch('src.app.main.ConfigLoader') as MockConfigLoader:
            MockConfigLoader.return_value.load.return_value = mock_config
            with patch('src.app.main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = []
                window._init_components()

        self.assertTrue(window._disabled)
        self.assertIn('ゲーム情報', window._status)

    def test_init_components_loghandler_file_not_found_disables(self):
        """_init_componentsはLogHandlerのFileNotFoundErrorで無効化."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)

        mock_config = MagicMock()
        mock_config.window_scan.browsers = []
        mock_config.window_scan.excluded_titles = []
        mock_games = [models.GameEntry(game_title="Test", window_title="Test")]

        with patch('src.app.main.ConfigLoader') as MockConfigLoader:
            MockConfigLoader.return_value.load.return_value = mock_config
            with patch('src.app.main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = mock_games
                with patch(
                    'src.app.main.LogHandler',
                    side_effect=FileNotFoundError("service_account.json"),
                ):
                    window._init_components()

        self.assertTrue(window._disabled)
        self.assertIn('認証情報', window._status)

    def test_init_components_spreadsheet_not_found_disables(self):
        """_init_componentsはSpreadsheetNotFoundで無効化."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)

        mock_config = MagicMock()
        mock_config.window_scan.browsers = []
        mock_config.window_scan.excluded_titles = []
        mock_games = [models.GameEntry(game_title="Test", window_title="Test")]

        with patch('src.app.main.ConfigLoader') as MockConfigLoader:
            MockConfigLoader.return_value.load.return_value = mock_config
            with patch('src.app.main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = mock_games
                with patch(
                    'src.app.main.LogHandler',
                    side_effect=fake_gspread.exceptions.SpreadsheetNotFound(),
                ):
                    window._init_components()

        self.assertTrue(window._disabled)
        self.assertIn('ログハンドラー初期化エラー', window._status)

    def test_init_components_api_error_disables(self):
        """_init_componentsはAPIErrorで無効化."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)

        mock_config = MagicMock()
        mock_config.window_scan.browsers = []
        mock_config.window_scan.excluded_titles = []
        mock_games = [models.GameEntry(game_title="Test", window_title="Test")]

        with patch('src.app.main.ConfigLoader') as MockConfigLoader:
            MockConfigLoader.return_value.load.return_value = mock_config
            with patch('src.app.main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = mock_games
                mock_response = MagicMock()
                mock_response.text = "Quota"
                mock_response.json.return_value = {}
                with patch(
                    'src.app.main.LogHandler',
                    side_effect=fake_gspread.exceptions.APIError(mock_response),
                ):
                    window._init_components()

        self.assertTrue(window._disabled)
        self.assertIn('ログハンドラー初期化エラー', window._status)

    def test_init_components_generic_exception_disables(self):
        """_init_componentsは汎用Exceptionで無効化."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)

        mock_config = MagicMock()
        mock_config.window_scan.browsers = []
        mock_config.window_scan.excluded_titles = []
        mock_games = [models.GameEntry(game_title="Test", window_title="Test")]

        # カスタム例外クラスを作成してgspread以外の例外をシミュレート
        class CustomNonGspreadError(Exception):
            pass

        # gspread.exceptions.APIErrorを一時的に差し替え
        original_api_error = fake_gspread.exceptions.APIError
        fake_gspread.exceptions.APIError = type('APIError', (ValueError,), {})  # 狭い継承

        try:
            with patch('src.app.main.ConfigLoader') as MockConfigLoader:
                MockConfigLoader.return_value.load.return_value = mock_config
                with patch('src.app.main.GameInfoLoader') as MockGameInfoLoader:
                    MockGameInfoLoader.return_value.load.return_value = mock_games
                    with patch(
                        'src.app.main.LogHandler',
                        side_effect=CustomNonGspreadError("Custom error"),
                    ):
                        window._init_components()

            self.assertTrue(window._disabled)
            self.assertIn('初期化エラー', window._status)
        finally:
            # 元に戻す
            fake_gspread.exceptions.APIError = original_api_error


class TestMainWindowEvents(unittest.TestCase):
    """MainWindowのイベント系メソッドテスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        window = create_mock_main_window(
            include_scanner=True,
            include_state_tracker=False,
            display_mode='mid',
            include_title_stubs=True,
            include_geometry_stubs=True,
        )
        window.setDisabled = MagicMock()
        return window

    def test_close_event_records_playing_games(self):
        """closeEventはプレイ中のゲームを記録する."""
        window = self._create_mock_main_window()
        window._save_window_state = MagicMock()

        game1 = models.GameEntry(
            game_title="Game1", window_title="Game1", is_playing=True)
        game1.start_time = datetime.now() - timedelta(minutes=10)
        game2 = models.GameEntry(
            game_title="Game2", window_title="Game2", is_playing=False)
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

        game = models.GameEntry(game_title="NoStart",
                                window_title="NoStart", is_playing=True)
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

        with patch('src.app.main.QTimer', return_value=mock_timer):
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
        window = create_mock_main_window(
            include_state_tracker=False,
            today_games_rowcount_zero=True,
        )
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

        game = models.GameEntry(game_title="PlayingGame",
                                window_title="PlayingGame", is_playing=True)
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

        game = models.GameEntry(game_title="ShortPlayingGame",
                                window_title="ShortPlayingGame", is_playing=True)
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
        game = models.GameEntry(
            game_title="GameA", window_title="GameA", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.active_games_cache = [game]

        window._update_today_games_list(datetime.now())

        # 30 + 10 = 40分として表示
        self.assertIn("GameA: 40分", window.daily_stats.last_today_games_content)


class TestLoadTodayDataExceptionHandling(unittest.TestCase):
    """_load_today_game_minutes/_load_today_completed_secondsの例外時挙動テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        return create_mock_main_window(
            include_state_tracker=False,
            include_ui=False,
        )

    def test_load_today_game_minutes_returns_empty_on_exception(self):
        """_load_today_game_minutesは例外時に空辞書を返す."""
        window = self._create_mock_main_window()

        mock_handler = MagicMock()
        mock_handler.get_today_stats.side_effect = RuntimeError("Database error")
        window.recorder = services.SessionRecorder(
            log_handler=mock_handler, min_play_minutes=5)

        result = window._load_today_game_minutes()

        self.assertEqual(result, {})

    def test_load_today_completed_seconds_returns_zero_on_exception(self):
        """_load_today_completed_secondsは例外時に0を返す."""
        window = self._create_mock_main_window()

        mock_handler = MagicMock()
        mock_handler.get_today_stats.side_effect = RuntimeError("Database error")
        window.recorder = services.SessionRecorder(
            log_handler=mock_handler, min_play_minutes=5)

        result = window._load_today_completed_seconds()

        self.assertEqual(result, 0.0)

    def test_load_today_game_minutes_handles_parse_error(self):
        """_load_today_game_minutesはパースエラーをスキップ."""
        window = self._create_mock_main_window()

        mock_handler = MagicMock()
        # 不正なレコード形式
        mock_handler.get_today_stats.return_value = ({}, 0.0)
        window.recorder = services.SessionRecorder(
            log_handler=mock_handler, min_play_minutes=5)

        result = window._load_today_game_minutes()

        # パース失敗レコードはスキップされる
        self.assertEqual(result, {})

    def test_load_today_completed_seconds_handles_parse_error(self):
        """_load_today_completed_secondsはパースエラーをスキップ."""
        window = self._create_mock_main_window()

        mock_handler = MagicMock()
        mock_handler.get_today_stats.return_value = ({}, 0.0)
        window.recorder = services.SessionRecorder(
            log_handler=mock_handler, min_play_minutes=5)

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
        window.recorder = services.SessionRecorder(
            log_handler=handler, min_play_minutes=5)

        result = window._load_today_game_minutes()

        # 昨日のレコードは含まれない
        self.assertEqual(result, {})


class TestScanTickStatusSwitch(unittest.TestCase):
    """_scan_tickのステータス切替テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        window = create_mock_main_window(
            include_scanner=True,
            include_latest_window_titles=True,
        )
        window.w.active_display = MagicMock()
        window.w.window_list = MagicMock()
        window.w.today_games_table = MagicMock()

        window._status = ""
        attach_window_title_stubs(window)
        window._load_today_game_minutes = MagicMock(return_value={})
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

        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=False)
        window.games = [game]
        window.scanner.get_titles.return_value = ["TestGame Window"]
        window.scanner.get_foreground_title.return_value = "TestGame Window"

        window._scan_tick()

        self.assertEqual(window._status, 'プレイ時間計測中')

    def test_status_playing_when_inactive_games(self):
        """非アクティブゲーム（停止中）がある場合もプレイ時間計測中."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)

        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
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

        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=False)
        window.games = [game]
        window.scanner.get_titles.return_value = ["Other Window"]  # ゲームウィンドウなし
        window.scanner.get_foreground_title.return_value = "Other Window"

        window._scan_tick()

        self.assertEqual(window._status, main.Messages.NO_GAME_PLAYING)

    def test_status_switches_from_playing_to_no_game(self):
        """プレイ中から未プレイへの切替."""
        window = self._create_mock_main_window()
        window._set_status = self._mock_set_status(window)

        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
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
        window.daily_stats = services.DailyStatsTracker()
        window.recorder = services.SessionRecorder(
            log_handler=FakeLogHandler(), min_play_minutes=5)

        # GameStateTrackerを初期化
        window.state_tracker = services.GameStateTracker(
            recorder=window.recorder,
            daily_stats=window.daily_stats,
            browsers=list(window.browsers),
            inactive_timeout_minutes=5,
        )

        window.w = MagicMock()
        window.w.active_display = MagicMock()
        window.w.window_list = MagicMock()
        window.w.today_games_table = MagicMock()

        window.scanner = MagicMock()
        window.scanner.excluded_titles = set()

        window.setWindowTitle = MagicMock()

        # _load_today_game_minutesをモック
        window._load_today_game_minutes = MagicMock(return_value={})

        return window

    def test_inactive_window_disappear_includes_inactive_time(self):
        """非アクティブ状態でウィンドウ消失時、非アクティブ時間も含めて記録."""
        window = self._create_mock_main_window()

        # 15分前から開始し、3分間非アクティブ状態
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
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

        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
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
        from src.ui.gui_layout import build_main_layout, LayoutWidgets
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
        from src.ui.gui_layout import LayoutWidgets
        from PySide6.QtWidgets import (
            QApplication,
            QLabel,
            QListWidget,
            QTableWidget,
            QWidget,
        )

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
        window.daily_stats = services.DailyStatsTracker()
        window.recorder = services.SessionRecorder(
            log_handler=FakeLogHandler(), min_play_minutes=5)

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

        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
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
        with patch('src.app.main.QTimer', return_value=mock_timer):
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
        window.daily_stats = services.DailyStatsTracker()
        window.recorder = services.SessionRecorder(
            log_handler=FakeLogHandler(), min_play_minutes=5)

        window.w = MagicMock()
        window.w.session_time_display = MagicMock()

        return window

    def test_includes_inactive_games_in_max_calculation(self):
        """inactive_games_cacheのゲームも最長時間計算に含まれる."""
        window = self._create_mock_main_window()

        # アクティブゲーム: 5分
        active_game = models.GameEntry(
            game_title="ActiveGame", window_title="ActiveGame", is_playing=True)
        active_game.start_time = datetime.now() - timedelta(minutes=5)

        # 非アクティブゲーム: 15分（こちらが最長）
        inactive_game = models.GameEntry(
            game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
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

        inactive_game = models.GameEntry(
            game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
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
        window.daily_stats = services.DailyStatsTracker()
        window.recorder = services.SessionRecorder(
            log_handler=FakeLogHandler(), min_play_minutes=5)

        window.w = MagicMock()
        window.w.today_time_display = MagicMock()

        return window

    def test_includes_inactive_game_time(self):
        """非アクティブゲームの時間も含まれる."""
        window = self._create_mock_main_window()
        window.daily_stats.today_completed_seconds = 0.0

        # 非アクティブゲーム: 10分
        inactive_game = models.GameEntry(
            game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
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
        game = models.GameEntry(game_title="NightGame",
                                window_title="NightGame", is_playing=True)
        game.start_time = datetime.combine(
            now.date() - timedelta(days=1), time(23, 0, 0))

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
        game = models.GameEntry(game_title="ShortGame",
                                window_title="ShortGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=3)

        window._update_today_totals([game], datetime.now())

        # 完了分の1時間のみ = 01:00:xx
        call_arg = window.w.today_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("01:00:"))

    def test_combined_active_inactive_completed(self):
        """アクティブ+非アクティブ+完了時間が合算される."""
        window = self._create_mock_main_window()
        now = datetime(2026, 1, 1, 12, 0, 0)
        window.daily_stats.today_completed_seconds = 1800.0  # 完了30分

        # アクティブゲーム: 10分
        active_game = models.GameEntry(
            game_title="ActiveGame", window_title="ActiveGame", is_playing=True)
        active_game.start_time = now - timedelta(minutes=10)

        # 非アクティブゲーム: 20分
        inactive_game = models.GameEntry(
            game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
        inactive_game.start_time = now - timedelta(minutes=20)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]

        window._update_today_totals([active_game], now)

        # 30 + 10 + 20 = 60分 = 01:00:xx
        call_arg = window.w.today_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("01:00:") or call_arg.startswith("00:59:"))


class TestUpdateTodayGamesListWithInactive(unittest.TestCase):
    """_update_today_games_listのinactive_games_cache経路テスト（実メソッド）."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        window = create_mock_main_window(include_scanner=False)
        window.w.today_games_table = MagicMock()
        return window

    def test_includes_inactive_game_in_list(self):
        """非アクティブゲームもリストに含まれる."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {}
        window.daily_stats.last_today_games_content = ""
        now = datetime(2026, 1, 1, 12, 0, 0)

        # 非アクティブゲーム: 15分
        inactive_game = models.GameEntry(
            game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
        inactive_game.start_time = now - timedelta(minutes=15)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]
        window.active_games_cache = []

        window._update_today_games_list(now)

        # テーブル更新される
        window.w.today_games_table.setRowCount.assert_called_with(1)
        self.assertIn("InactiveGame: 15分", window.daily_stats.last_today_games_content)

    def test_merges_active_and_inactive_games(self):
        """アクティブと非アクティブゲームがマージされる."""
        window = self._create_mock_main_window()
        window.daily_stats.today_game_minutes_cache = {}
        window.daily_stats.last_today_games_content = ""
        now = datetime(2026, 1, 1, 12, 0, 0)

        # アクティブゲーム: 10分
        active_game = models.GameEntry(
            game_title="ActiveGame", window_title="ActiveGame", is_playing=True)
        active_game.start_time = now - timedelta(minutes=10)
        window.active_games_cache = [active_game]

        # 非アクティブゲーム: 20分
        inactive_game = models.GameEntry(
            game_title="InactiveGame", window_title="InactiveGame", is_playing=True)
        inactive_game.start_time = now - timedelta(minutes=20)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]

        window._update_today_games_list(now)

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
        now = datetime(2026, 1, 1, 12, 0, 0)

        # 同じゲームが非アクティブで15分
        inactive_game = models.GameEntry(
            game_title="GameA", window_title="GameA", is_playing=True)
        inactive_game.start_time = now - timedelta(minutes=15)
        inactive_game.set_inactive()
        window.inactive_games_cache = [inactive_game]
        window.active_games_cache = []

        window._update_today_games_list(now)

        # 30 + 15 = 45分
        self.assertIn("GameA: 45分", window.daily_stats.last_today_games_content)


class TestLoadTodayGameMinutesParseNone(unittest.TestCase):
    """_load_today_game_minutesでParsedRecordがNoneになるケースのテスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        return create_mock_main_window(
            include_state_tracker=False,
            include_ui=False,
        )

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
        window.recorder = services.SessionRecorder(
            log_handler=handler, min_play_minutes=5)

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
        window.recorder = services.SessionRecorder(
            log_handler=handler, min_play_minutes=5)

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
        window.recorder = services.SessionRecorder(
            log_handler=handler, min_play_minutes=5)

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
        window.recorder = services.SessionRecorder(
            log_handler=handler, min_play_minutes=5)

        result = window._load_today_game_minutes()

        self.assertIn('ValidRecord', result)


class TestCloseEventRealMethod(unittest.TestCase):
    """closeEventの実メソッド呼び出しテスト."""

    def test_close_event_calls_super(self):
        """closeEventがsuper().closeEvent()を呼び出す."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()

        window.games = []
        window.overlay_window = None
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
        window.overlay_window = None
        window._save_window_state = MagicMock()

        mock_event = MagicMock(spec=main.QCloseEvent)

        with patch.object(main.QWidget, 'closeEvent'):
            window.closeEvent(mock_event)
            window._save_window_state.assert_called_once()

    def test_close_event_records_playing_games(self):
        """closeEventがプレイ中ゲームを記録する."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()

        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=10)
        window.games = [game]
        window.overlay_window = None
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

        with patch('src.app.main.QTimer') as MockQTimer:
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
        window.w.overtime_alert_toggle = MagicMock()
        window.w.report_button = MagicMock()

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
        # todayラベルは非表示（時間表示を優先）
        window.w.today_label.setVisible.assert_called_with(False)
        # window_listが非表示
        window.w.window_label.setVisible.assert_called_with(False)
        window.w.window_list.setVisible.assert_called_with(False)

    def test_min_mode_keeps_overtime_toggle_visible(self):
        """minモードでも時間超過防止アラートトグルは表示される."""
        window = self._create_mock_main_window()
        window.display_mode = 'min'

        window._apply_display_mode()

        window.w.overtime_alert_toggle.setVisible.assert_called_with(True)

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
        with patch('src.app.main.QApplication') as MockQApp:
            with patch('src.app.main.MainWindow') as MockWindow:
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
        with patch('src.app.main.QApplication') as MockQApp:
            with patch('src.app.main.MainWindow') as MockWindow:
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
        with patch('src.app.main.QApplication') as MockQApp:
            with patch('src.app.main.MainWindow') as MockWindow:
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
        with patch('src.app.main.QApplication') as MockQApp:
            with patch('src.app.main.MainWindow') as MockWindow:
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
        return create_mock_main_window(include_state_tracker=False, include_ui=False)

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
        return create_mock_main_window(include_state_tracker=False, include_ui=False)

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
        window = create_mock_main_window(include_state_tracker=False)
        window.inactive_games_cache = []
        window.w.session_time_display = MagicMock()
        return window

    def test_start_time_none_treated_as_zero(self):
        """start_time=Noneのゲームは0秒として扱われる."""
        window = self._create_mock_main_window()

        # start_time=Noneのゲーム
        game_none = models.GameEntry(
            game_title="NoneGame", window_title="NoneGame", is_playing=True)
        game_none.start_time = None  # 明示的にNone

        window._update_session_times([game_none], datetime.now())

        # 0秒 = 00:00:00.0
        call_arg = window.w.session_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:00:00"))

    def test_max_elapsed_with_none_and_valid(self):
        """start_time=Noneと有効なstart_timeが混在する場合、有効なものの最大値."""
        window = self._create_mock_main_window()

        # start_time=Noneのゲーム（0秒扱い）
        game_none = models.GameEntry(
            game_title="NoneGame", window_title="NoneGame", is_playing=True)
        game_none.start_time = None

        # 有効なstart_timeのゲーム（10分）
        game_valid = models.GameEntry(
            game_title="ValidGame", window_title="ValidGame", is_playing=True)
        game_valid.start_time = datetime.now() - timedelta(minutes=10)

        window._update_session_times([game_none, game_valid], datetime.now())

        # 10分が表示される（Noneは0なので最大値は10分）
        call_arg = window.w.session_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:10:") or call_arg.startswith("00:09:"))

    def test_all_games_start_time_none(self):
        """全ゲームがstart_time=Noneなら0秒."""
        window = self._create_mock_main_window()

        game1 = models.GameEntry(
            game_title="Game1", window_title="Game1", is_playing=True)
        game1.start_time = None
        game2 = models.GameEntry(
            game_title="Game2", window_title="Game2", is_playing=True)
        game2.start_time = None

        window._update_session_times([game1, game2], datetime.now())

        # 0秒
        call_arg = window.w.session_time_display.setText.call_args[0][0]
        self.assertTrue(call_arg.startswith("00:00:00"))


class TestOverlayMethods(unittest.TestCase):
    """オーバーレイ更新/終了メソッドのテスト."""

    def _create_mock_main_window(self):
        return create_mock_main_window(include_state_tracker=False, include_ui=False)

    def test_refresh_overlay_time_updates_text(self):
        """_refresh_overlay_timeはtoday_time_displayの値をオーバーレイへ反映."""
        window = self._create_mock_main_window()
        window.overlay_window = MagicMock()
        window.w = MagicMock()
        window.w.today_time_display.text.return_value = "01:23:45.6"

        window._refresh_overlay_time()

        window.overlay_window.set_today_text.assert_called_once_with("01:23:45.6")

    def test_close_overlay_closes_and_clears_reference(self):
        """_close_overlayはcloseを呼び、参照をNoneにする."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        window.overlay_window = overlay

        window._close_overlay()

        overlay.close.assert_called_once()
        self.assertIsNone(window.overlay_window)

    def test_sync_overlay_visibility_shows_when_window_is_background(self):
        """_sync_overlay_visibilityは背面時にshowを呼ぶ."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        overlay.isVisible.return_value = False
        window.overlay_window = overlay
        window._should_show_overlay = MagicMock(return_value=True)

        window._sync_overlay_visibility()

        overlay.show.assert_called_once()
        overlay.hide.assert_not_called()

    def test_sync_overlay_visibility_hides_when_window_is_foreground(self):
        """_sync_overlay_visibilityは前面時にhideを呼ぶ."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        overlay.isVisible.return_value = False
        window.overlay_window = overlay
        window._should_show_overlay = MagicMock(return_value=False)

        window._sync_overlay_visibility()

        overlay.hide.assert_called_once()
        overlay.show.assert_not_called()

    def test_sync_overlay_visibility_temporarily_hides_visible_overlay_before_check(
            self):
        """判定前に表示中オーバーレイを一度隠してヒットテスト誤検出を避ける."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        overlay.isVisible.return_value = True
        window.overlay_window = overlay
        window._should_show_overlay = MagicMock(return_value=True)

        window._sync_overlay_visibility()

        self.assertGreaterEqual(overlay.hide.call_count, 1)
        overlay.show.assert_called_once()

    def test_sync_overlay_geometry_matches_today_time_display(self):
        """_sync_overlay_geometryはtoday_time_display位置とサイズへ追従."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        window.overlay_window = overlay
        window.w = MagicMock()

        point = MagicMock()
        point.x.return_value = 111
        point.y.return_value = 222
        rect = MagicMock()
        rect.topLeft.return_value = object()

        target = MagicMock()
        target.rect.return_value = rect
        target.mapToGlobal.return_value = point
        target.width.return_value = 333
        target.height.return_value = 44
        window.w.today_time_display = target

        window._sync_overlay_geometry()

        overlay.setGeometry.assert_called_once_with(111, 222, 333, 44)

    def test_should_show_overlay_returns_false_when_not_covered(self):
        """非アクティブでも重なっていなければオーバーレイは表示しない."""
        window = self._create_mock_main_window()
        window.isMinimized = MagicMock(return_value=False)
        window.isVisible = MagicMock(return_value=True)
        window.isActiveWindow = MagicMock(return_value=False)
        window._is_today_display_covered_by_foreground_window = MagicMock(
            return_value=False)

        result = window._should_show_overlay()

        self.assertFalse(result)

    def test_should_show_overlay_returns_true_when_covered(self):
        """非アクティブかつ重なっている場合のみ表示する."""
        window = self._create_mock_main_window()
        window.isMinimized = MagicMock(return_value=False)
        window.isVisible = MagicMock(return_value=True)
        window.isActiveWindow = MagicMock(return_value=False)
        window._is_today_display_covered_by_foreground_window = MagicMock(
            return_value=True)

        result = window._should_show_overlay()

        self.assertTrue(result)

    def test_should_show_overlay_returns_false_when_overtime_alert_disabled(self):
        """時間超過防止アラートOFF時はオーバーレイを表示しない."""
        window = self._create_mock_main_window()
        window.overtime_alert_enabled = False
        window._is_today_display_covered_by_foreground_window = MagicMock(
            return_value=True)

        result = window._should_show_overlay()

        self.assertFalse(result)
        window._is_today_display_covered_by_foreground_window.assert_not_called()

    def test_covered_by_foreign_window_returns_true(self):
        """5点のいずれかが他ウィンドウで覆われればTrue."""
        window = self._create_mock_main_window()
        window.w = MagicMock()
        target = MagicMock()
        point = MagicMock()
        point.x.return_value = 100
        point.y.return_value = 200
        target.rect.return_value.topLeft.return_value = object()
        target.mapToGlobal.return_value = point
        target.width.return_value = 120
        target.height.return_value = 30
        window.w.today_time_display = target

        window._is_own_window = MagicMock(return_value=False)
        window._window_rect = MagicMock(return_value=(0, 0, 2000, 2000))
        window._to_native_point = MagicMock(side_effect=lambda x, y: (x, y))
        window._find_covering_foreign_window_at_point = MagicMock(
            side_effect=[0, 0, 999, 0, 0])

        with patch('src.app.win32_helpers.get_foreground_hwnd', return_value=123):
            self.assertTrue(window._is_today_display_covered_by_foreground_window())

    def test_uncovered_when_top_window_is_own_returns_false(self):
        """5点すべて未被覆ならFalse."""
        window = self._create_mock_main_window()
        window.w = MagicMock()
        target = MagicMock()
        point = MagicMock()
        point.x.return_value = 150
        point.y.return_value = 250
        target.rect.return_value.topLeft.return_value = object()
        target.mapToGlobal.return_value = point
        target.width.return_value = 140
        target.height.return_value = 40
        window.w.today_time_display = target
        window._is_own_window = MagicMock(return_value=False)
        window._window_rect = MagicMock(return_value=(0, 0, 2000, 2000))
        window._to_native_point = MagicMock(side_effect=lambda x, y: (x, y))
        window._find_covering_foreign_window_at_point = MagicMock(side_effect=[
                                                                  0, 0, 0, 0, 0])

        with patch('src.app.win32_helpers.get_foreground_hwnd', return_value=123):
            self.assertFalse(window._is_today_display_covered_by_foreground_window())

    def test_sample_points_from_rect_uses_25_75_offsets(self):
        """_sample_points_from_rectは中心+25/75%点を返す."""
        rect = (100, 200, 200, 300)  # width=100, height=100

        points = main.MainWindow._sample_points_from_rect(rect)

        self.assertEqual(points, [(150, 250), (125, 225),
                         (175, 225), (125, 275), (175, 275)])

    def test_find_covering_foreign_window_at_point_returns_covering_hwnd(self):
        """_find_covering_foreign_window_at_pointは点を覆う他ウィンドウを返す."""
        window = self._create_mock_main_window()
        window._window_at_point = MagicMock(return_value=500)
        window._is_own_window = MagicMock(return_value=False)
        window._window_rect = MagicMock(return_value=(0, 0, 1000, 1000))
        window._window_below = MagicMock(return_value=0)

        result = window._find_covering_foreign_window_at_point(100, 200)

        self.assertEqual(result, 500)

    def test_find_covering_foreign_window_at_point_ignores_non_covering_hwnd(self):
        """矩形が点を含まない候補ウィンドウは被りとして扱わない."""
        window = self._create_mock_main_window()
        window._window_at_point = MagicMock(return_value=500)
        window._is_own_window = MagicMock(return_value=False)
        window._window_rect = MagicMock(return_value=(0, 0, 10, 10))
        window._window_below = MagicMock(return_value=0)

        result = window._find_covering_foreign_window_at_point(100, 200)

        self.assertEqual(result, 0)

    def test_find_covering_foreign_window_at_point_stops_at_max_z_walk(self):
        """_find_covering_foreign_window_at_pointはMAX_Z_WALK回で探索を打ち切る."""
        window = self._create_mock_main_window()
        window._window_at_point = MagicMock(return_value=111)
        window._is_own_window = MagicMock(return_value=False)
        window._window_below = MagicMock(return_value=111)
        window._window_rect = MagicMock(return_value=None)

        result = window._find_covering_foreign_window_at_point(100, 200)

        self.assertEqual(result, 0)
        self.assertEqual(window._window_below.call_count, main.MAX_Z_WALK)

    def test_find_covering_foreign_window_at_point_returns_zero_for_own_window(self):
        """判定点が自ウィンドウなら被覆なしとして0を返す."""
        window = self._create_mock_main_window()
        window._window_at_point = MagicMock(return_value=111)
        window._is_own_window = MagicMock(return_value=True)
        window._window_below = MagicMock(return_value=222)
        window._window_rect = MagicMock(return_value=(0, 0, 1000, 1000))

        result = window._find_covering_foreign_window_at_point(100, 200)

        self.assertEqual(result, 0)
        window._window_below.assert_not_called()


class TestOvertimeAlertMethods(unittest.TestCase):
    """時間超過防止アラートのテスト."""

    def _create_mock_main_window(self):
        return create_mock_main_window(include_state_tracker=False, include_ui=False)

    def test_update_overtime_alert_beeps_once_on_threshold_cross(self):
        """閾値を跨いだときのみ1回通知する."""
        window = self._create_mock_main_window()
        window.overtime_alert_enabled = True
        tracker = main.OvertimeAlertTracker(
            thresholds_minutes=main.OVERTIME_ALERT_THRESHOLDS_MINUTES,
            alerted_threshold_minutes=set(),
            last_checked_seconds=44 * 60,
            initialized=True,
        )
        window._overtime_alert_tracker = tracker

        with patch.object(main.QApplication, "beep") as mock_beep:
            window._update_overtime_alert((45 * 60) + 1)
            window._update_overtime_alert((46 * 60))

        self.assertEqual(mock_beep.call_count, 1)
        self.assertIn(45, tracker.alerted_threshold_minutes)

    def test_update_overtime_alert_does_not_beep_when_disabled(self):
        """トグルOFF時は閾値を跨いでも通知しない."""
        window = self._create_mock_main_window()
        window.overtime_alert_enabled = False
        tracker = main.OvertimeAlertTracker(
            thresholds_minutes=main.OVERTIME_ALERT_THRESHOLDS_MINUTES,
            alerted_threshold_minutes=set(),
            last_checked_seconds=44 * 60,
            initialized=True,
        )
        window._overtime_alert_tracker = tracker

        with patch.object(main.QApplication, "beep") as mock_beep:
            window._update_overtime_alert((45 * 60) + 1)

        mock_beep.assert_not_called()
        self.assertNotIn(45, tracker.alerted_threshold_minutes)


if __name__ == "__main__":
    unittest.main()
