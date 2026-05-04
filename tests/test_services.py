# pyright: reportAttributeAccessIssue=false, reportArgumentType=false,
# reportCallIssue=false, reportOptionalMemberAccess=false
"""domain.py / adapters.py のユニットテスト."""

from tests.test_stubs import fake_gspread, FakeLogHandler

import pygetwindow
from src.core.text_utils import normalize_title
from src.core.adapters import GameInfoLoader, Messages, SessionRecorder, WindowScanner
from src.core import adapters as services
from src.core import domain
from src.core import models
from src.core.domain import (
    DailyStatsTracker,
    GameStateTracker,
    MIN_PLAY_MINUTES,
    ScanResult,
)
from src.core.time_utils import SECONDS_PER_MINUTE
from src.app import main
import sys
import unittest
from datetime import datetime, date, time, timedelta
from unittest.mock import MagicMock, patch


# servicesモジュールにpygetwindowのスタブを設定
services.gw = pygetwindow


def stable_today_now() -> datetime:
    """Return a same-day timestamp that does not cross midnight in tests."""
    return datetime.combine(datetime.now().date(), time(12, 0, 0))


class TestSessionRecorder(unittest.TestCase):
    def test_record_over_threshold_appends(self):
        handler = FakeLogHandler()
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(
            game_title="LongPlay",
            window_title="LongPlay",
            play_with_friends=True,
            is_playing=True)
        now = stable_today_now()
        game.start_time = now - timedelta(minutes=6)

        with patch.object(services, "datetime") as mock_datetime, patch.object(
            models,
            "datetime",
        ) as mock_model_datetime:
            mock_datetime.now.return_value = now
            mock_model_datetime.now.return_value = now
            recorder.record(game)

        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)
        self.assertEqual(len(handler.records), 1)
        self.assertEqual(handler.records[0]['index'], 1)
        self.assertEqual(handler.records[0]['title'], "LongPlay")
        self.assertTrue(handler.records[0]['play_with_friends'])

    def test_record_under_threshold_skips(self):
        handler = FakeLogHandler()
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(
            game_title="ShortPlay",
            window_title="ShortPlay",
            play_with_friends=False,
            is_playing=True)
        game.start_time = datetime.now() - timedelta(minutes=2)

        recorder.record(game)

        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)
        self.assertEqual(handler.records, [])


class TestSessionRecorderWithTimes(unittest.TestCase):
    """SessionRecorder.record_with_times()のテスト."""

    def test_record_with_times_saves_record(self):
        """record_with_times()で指定した時刻でレコードを保存."""
        handler = FakeLogHandler()
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", is_playing=True)
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
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(game_title="TestGame", window_title="TestGame")

        start = datetime(2026, 1, 18, 10, 0, 0)
        end = datetime(2026, 1, 18, 10, 3, 0)  # 3分
        result = recorder.record_with_times(game, start, end)

        self.assertIsNone(result)
        self.assertEqual(len(handler.records), 0)


class TestWindowScannerForeground(unittest.TestCase):
    """WindowScanner.get_foreground_title()のテスト."""

    def test_get_foreground_title_returns_none_when_no_active_window(self):
        """アクティブウィンドウがない場合はNoneを返す."""
        scanner = services.WindowScanner(excluded_titles=[])
        # pygetwindow.getActiveWindow()はスタブではNoneを返す想定
        result = scanner.get_foreground_title()
        self.assertIsNone(result)


class TestDailyStatsTracker(unittest.TestCase):
    """DailyStatsTrackerのテスト."""

    def test_initial_state(self):
        """初期状態の確認."""
        tracker = domain.DailyStatsTracker()
        self.assertEqual(tracker.today_completed_seconds, 0.0)
        self.assertEqual(tracker.today_game_minutes_cache, {})
        self.assertEqual(tracker.last_today_games_content, "")

    def test_add_completed_seconds(self):
        """完了秒数の追加."""
        tracker = domain.DailyStatsTracker()
        tracker.add_completed_seconds(300)
        self.assertEqual(tracker.today_completed_seconds, 300)
        tracker.add_completed_seconds(150)
        self.assertEqual(tracker.today_completed_seconds, 450)

    def test_update_game_minutes_cache(self):
        """ゲーム時間キャッシュの更新."""
        tracker = domain.DailyStatsTracker()
        cache = {"Game1": 30.0, "Game2": 60.0}
        tracker.update_game_minutes_cache(cache)
        self.assertEqual(tracker.today_game_minutes_cache, cache)

    def test_check_day_change_same_day(self):
        """同日ではリセットされない."""
        current_date = datetime(2026, 1, 18).date()
        tracker = domain.DailyStatsTracker(get_current_date=lambda: current_date)
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

        tracker = domain.DailyStatsTracker(get_current_date=lambda: current_date[0])
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

        tracker = domain.DailyStatsTracker(get_current_date=lambda: current_date[0])

        # 日付変更
        current_date[0] = day2
        result1 = tracker.check_day_change()
        self.assertTrue(result1)

        # 同日の再チェック
        result2 = tracker.check_day_change()
        self.assertFalse(result2)


class TestWindowScanner(unittest.TestCase):
    """WindowScannerのテスト."""

    def test_excluded_titles_initialized(self):
        """除外リストが正しく設定される."""
        excluded = ["Program Manager", "Settings"]
        scanner = services.WindowScanner(excluded_titles=excluded)
        self.assertEqual(scanner.excluded_titles, set(excluded))

    def test_excluded_titles_is_set(self):
        """除外リストがsetとして保持される."""
        excluded = ["Title1", "Title2", "Title1"]  # 重複あり
        scanner = services.WindowScanner(excluded_titles=excluded)
        self.assertEqual(len(scanner.excluded_titles), 2)


class TestSessionRecorderRecordWithTimesNoStateChange(unittest.TestCase):
    """record_with_times()がゲーム状態を変更しないことのテスト."""

    def test_game_state_unchanged_after_record_with_times(self):
        """record_with_times()後もゲームの状態は変わらない."""
        handler = FakeLogHandler()
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)

        original_start = datetime(2026, 1, 18, 10, 0, 0)
        game = models.GameEntry(
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
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)

        game = models.GameEntry(
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
        """モックConfigを作成."""
        config = MagicMock()
        config.log_handler.cert_file_path = 'fake.json'
        config.game_info.sheet_key = 'fake_key'
        config.game_info.sheet_gid = 123
        return config

    def _empty_store(self):
        store = MagicMock()
        store.has_any_games.return_value = False
        store.import_records.return_value = 0
        store.load_games.return_value = []
        return store

    def test_load_uses_local_store_when_games_exist(self):
        """ローカルDBにゲーム情報がある場合はスプレッドシートを読まない."""
        store = MagicMock()
        store.has_any_games.return_value = True
        store.load_games.return_value = [
            models.GameEntry(game_title="Local", window_title="Local")
        ]
        config = self._create_mock_config()
        loader = services.GameInfoLoader(config, game_store=store)

        result = loader.load()

        self.assertEqual(result[0].game_title, "Local")
        store.load_games.assert_called_once()

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_load_file_not_found_raises(self, mock_sa):
        """認証ファイルが見つからない場合は起動側へ再送出する."""
        mock_sa.side_effect = FileNotFoundError("fake.json not found")
        config = self._create_mock_config()
        loader = services.GameInfoLoader(config, game_store=self._empty_store())

        with self.assertRaises(FileNotFoundError):
            loader.load()

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_load_spreadsheet_not_found_returns_empty(self, mock_sa):
        """スプレッドシートが見つからない場合は空リストを返す."""
        mock_sa.side_effect = fake_gspread.exceptions.SpreadsheetNotFound("Not found")
        config = self._create_mock_config()
        loader = services.GameInfoLoader(config, game_store=self._empty_store())

        result = loader.load()

        self.assertEqual(result, [])

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_load_worksheet_not_found_returns_empty(self, mock_sa):
        """ワークシートが見つからない場合は空リストを返す."""
        mock_gc = MagicMock()
        mock_gc.open_by_key.return_value.get_worksheet_by_id.side_effect = \
            fake_gspread.exceptions.WorksheetNotFound("gid not found")
        mock_sa.return_value = mock_gc
        config = self._create_mock_config()
        loader = services.GameInfoLoader(config, game_store=self._empty_store())

        result = loader.load()

        self.assertEqual(result, [])

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_load_api_error_returns_empty(self, mock_sa):
        """APIエラーの場合は空リストを返す."""
        mock_response = MagicMock()
        mock_response.text = "API quota exceeded"
        mock_response.json.return_value = {}
        mock_sa.side_effect = fake_gspread.exceptions.APIError(mock_response)
        config = self._create_mock_config()
        loader = services.GameInfoLoader(config, game_store=self._empty_store())

        result = loader.load()

        self.assertEqual(result, [])

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_load_generic_exception_is_reraised(self, mock_sa):
        """想定外の例外は握りつぶさず再送出する."""
        mock_sa.side_effect = RuntimeError("Unexpected error")
        config = self._create_mock_config()
        loader = services.GameInfoLoader(config, game_store=self._empty_store())

        with self.assertRaises(RuntimeError):
            loader.load()

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_load_success_returns_entries(self, mock_sa):
        """正常に読み込めた場合はGameEntryリストを返す."""
        mock_sheet = MagicMock()
        mock_sheet.get_all_records.return_value = [
            {'game_title': 'Game1', 'window_title': 'Game1',
                'play_with_friends': 'TRUE', 'is_browser_game': 'FALSE'},
            {'game_title': 'Game2', 'window_title': 'Game2 Window',
                'play_with_friends': 'FALSE', 'is_browser_game': 'TRUE'},
        ]
        mock_gc = MagicMock()
        mock_gc.open_by_key.return_value.get_worksheet_by_id.return_value = mock_sheet
        mock_sa.return_value = mock_gc
        config = self._create_mock_config()
        store = self._empty_store()
        store.import_records.return_value = 2
        store.load_games.return_value = [
            models.GameEntry(
                game_title='Game1',
                window_title='Game1',
                play_with_friends=True,
            ),
            models.GameEntry(
                game_title='Game2',
                window_title='Game2 Window',
                is_browser_game=True,
            ),
        ]
        loader = services.GameInfoLoader(config, game_store=store)

        result = loader.load()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].game_title, 'Game1')
        self.assertTrue(result[0].play_with_friends)
        self.assertEqual(result[1].game_title, 'Game2')
        self.assertTrue(result[1].is_browser_game)
        store.import_records.assert_called_once_with(mock_sheet.get_all_records.return_value)


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

        with patch.object(services.gw, 'getAllWindows', return_value=mock_windows):
            scanner = services.WindowScanner(excluded_titles=["Program Manager"])
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

        with patch.object(services.gw, 'getAllWindows', return_value=mock_windows):
            scanner = services.WindowScanner(excluded_titles=[])
            titles = scanner.get_titles()

        self.assertEqual(titles, ["Valid Title"])

    def test_returns_unique_titles(self):
        """重複するタイトルは1つにまとめられる."""
        mock_windows = [
            MagicMock(title="Same Title"),
            MagicMock(title="Same Title"),
            MagicMock(title="Different Title"),
        ]

        with patch.object(services.gw, 'getAllWindows', return_value=mock_windows):
            scanner = services.WindowScanner(excluded_titles=[])
            titles = scanner.get_titles()

        self.assertEqual(len(titles), 2)
        self.assertIn("Same Title", titles)
        self.assertIn("Different Title", titles)


class TestUpdateGameStates(unittest.TestCase):
    """_update_game_states()の状態遷移テスト."""

    def setUp(self):
        """テスト用のモックオブジェクトを設定."""
        self.handler = FakeLogHandler()
        self.recorder = services.SessionRecorder(
            log_handler=self.handler, min_play_minutes=5)
        self.daily_stats = domain.DailyStatsTracker()

    def test_window_disappear_triggers_record(self):
        """ウィンドウ消失時にrecord()が呼ばれる."""
        game = models.GameEntry(
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
        normalized_titles = [normalize_title(title) for title in window_titles]
        normalized_browsers = [normalize_title(browser) for browser in browsers]
        window_exists = any(
            game.matches_window(title, normalized_browsers)
            for title in normalized_titles
        )
        self.assertFalse(window_exists)

        # record()を呼ぶ
        recorded = self.recorder.record(game)

        self.assertIsNotNone(recorded)
        self.assertFalse(game.is_playing)
        self.assertEqual(len(self.handler.records), 1)

    def test_inactive_5min_timeout_triggers_record_with_times(self):
        """非アクティブ5分超過でrecord_with_times()が呼ばれ、状態がリセットされる."""
        game = models.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        fixed_now = datetime(2026, 1, 1, 12, 0, 0)
        # 開始から非アクティブ化までの時間が5分以上になるように設定
        start = fixed_now - timedelta(minutes=15)
        inactive_since = fixed_now - timedelta(minutes=6)  # 6分前から非アクティブ
        game.start_time = start
        game.inactive_since = inactive_since

        # 5分超過を検出
        inactive_seconds = game.get_inactive_seconds(now=fixed_now)
        self.assertGreaterEqual(inactive_seconds, 5 * 60)

        # record_with_timesを呼ぶ（start_timeからinactive_sinceまでは9分なので記録される）
        recorded = self.recorder.record_with_times(
            game, game.start_time, game.inactive_since)

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
        game = models.GameEntry(
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
        game = models.GameEntry(
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


class TestUpdateGameStatesIntegration(unittest.TestCase):
    """_update_game_states()の統合テスト."""

    def setUp(self):
        """テスト用のモックオブジェクトを設定."""
        self.handler = FakeLogHandler()
        self.recorder = services.SessionRecorder(
            log_handler=self.handler, min_play_minutes=5)
        self.daily_stats = domain.DailyStatsTracker()
        self.browsers = ['Chrome', 'Firefox']

    def _run_update_game_states(self, games, window_titles, foreground_title):
        """_update_game_statesのロジックを再現して実行."""
        active_games = []
        inactive_games = []

        normalized_titles = [normalize_title(title) for title in window_titles]
        normalized_foreground = (
            normalize_title(foreground_title) if foreground_title else None
        )
        normalized_browsers = [normalize_title(browser) for browser in self.browsers]

        for game in games:
            window_exists = any(
                game.matches_window(title, normalized_browsers)
                for title in normalized_titles
            )
            is_foreground = (
                normalized_foreground is not None
                and game.matches_window(normalized_foreground, normalized_browsers)
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
                    if (
                            inactive_seconds
                            >= main.INACTIVE_TIMEOUT_MINUTES * main.SECONDS_PER_MINUTE
                    ):
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
        game = models.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        now = stable_today_now()
        game.start_time = now - timedelta(minutes=10)

        with patch.object(services, "datetime") as mock_datetime, patch.object(
            models,
            "datetime",
        ) as mock_model_datetime:
            mock_datetime.now.return_value = now
            mock_model_datetime.now.return_value = now
            active, inactive = self._run_update_game_states([game], [], None)

        self.assertEqual(len(active), 0)
        self.assertEqual(len(inactive), 0)
        self.assertFalse(game.is_playing)
        self.assertEqual(len(self.handler.records), 1)
        self.assertGreater(self.daily_stats.today_completed_seconds, 0)

    def test_full_flow_foreground_returns_active(self):
        """フォアグラウンドで開始するとactiveリストに返される."""
        game = models.GameEntry(
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
        game = models.GameEntry(
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
        game = models.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        fixed_now = datetime(2026, 1, 1, 12, 0, 0)
        game.start_time = fixed_now - timedelta(minutes=15)
        game.inactive_since = fixed_now - timedelta(minutes=6)

        active, inactive = self._run_update_game_states(
            [game], ["TestGame Window", "Other Window"], "Other Window"
        )

        self.assertEqual(len(active), 0)
        self.assertEqual(len(inactive), 0)
        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)
        self.assertIsNone(game.inactive_since)
        self.assertEqual(len(self.handler.records), 1)
        self.assertGreaterEqual(self.daily_stats.today_completed_seconds, 0)


class TestWindowScannerGetForegroundTitle(unittest.TestCase):
    """WindowScanner.get_foreground_title()のテスト."""

    def test_returns_title_when_active_window_exists(self):
        """アクティブウィンドウがある場合はタイトルを返す."""
        mock_window = MagicMock()
        mock_window.title = "Active Window Title"

        with patch.object(services.gw, 'getActiveWindow', return_value=mock_window):
            scanner = services.WindowScanner(excluded_titles=[])
            result = scanner.get_foreground_title()

        self.assertEqual(result, "Active Window Title")

    def test_returns_none_when_no_active_window(self):
        """アクティブウィンドウがない場合はNoneを返す."""
        with patch.object(services.gw, 'getActiveWindow', return_value=None):
            scanner = services.WindowScanner(excluded_titles=[])
            result = scanner.get_foreground_title()

        self.assertIsNone(result)

    def test_returns_none_when_title_is_empty(self):
        """タイトルが空の場合はNoneを返す."""
        mock_window = MagicMock()
        mock_window.title = ""

        with patch.object(services.gw, 'getActiveWindow', return_value=mock_window):
            scanner = services.WindowScanner(excluded_titles=[])
            result = scanner.get_foreground_title()

        self.assertIsNone(result)

    def test_returns_none_when_exception_occurs(self):
        """例外発生時はNoneを返す（例外は吸収される）."""
        with patch.object(
            services.gw,
            'getActiveWindow',
            side_effect=RuntimeError("Test error"),
        ):
            scanner = services.WindowScanner(excluded_titles=[])
            result = scanner.get_foreground_title()

        self.assertIsNone(result)


class TestRecordSegmentsCrossDayTodaySeconds(unittest.TestCase):
    """_record_segmentsの戻り値（today_seconds）の跨日ケーステスト."""

    def test_cross_day_returns_only_today_seconds(self):
        """跨日記録は当日分のみtoday_secondsに加算."""
        handler = FakeLogHandler()
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(game_title="CrossDayGame", window_title="CrossDayGame")

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
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(game_title="YesterdayGame",
                                window_title="YesterdayGame")

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
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(game_title="TodayGame", window_title="TodayGame")

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
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(game_title="MultiDayGame", window_title="MultiDayGame")

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

        entry = services.GameInfoLoader._record_to_entry(record)

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

        entry = services.GameInfoLoader._record_to_entry(record)

        self.assertTrue(entry.play_with_friends)
        self.assertTrue(entry.is_browser_game)

    def test_handles_missing_optional_fields(self):
        """オプションフィールドが欠落している場合はデフォルト値."""
        record = {
            'game_title': 'MinimalGame',
            'window_title': 'MinimalGame',
        }

        entry = services.GameInfoLoader._record_to_entry(record)

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

        entry = services.GameInfoLoader._record_to_entry(record)

        self.assertEqual(entry.game_title, '12345')
        self.assertEqual(entry.window_title, '67890')

    def test_empty_window_title_emits_warning(self):
        """window_title が空の場合は警告ログを出す."""
        record = {
            'game_title': 'EmptyWindowTitleGame',
            'window_title': '   ',
            'play_with_friends': 'FALSE',
            'is_browser_game': 'FALSE',
        }

        with self.assertLogs('src.core.adapters', level='WARNING') as captured:
            entry = services.GameInfoLoader._record_to_entry(record)

        self.assertEqual(entry.window_title, '   ')
        self.assertTrue(
            any('window_title が空' in message for message in captured.output))


class TestSessionRecorderSaveToSpreadsheet(unittest.TestCase):
    """SessionRecorder._save_to_spreadsheetのテスト."""

    def test_save_success_returns_true(self):
        """保存成功時にTrueを返す."""
        handler = FakeLogHandler()
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", play_with_friends=True)

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
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(game_title="TestGame", window_title="TestGame")

        start_time = datetime(2026, 1, 18, 10, 0, 0)
        end_time = datetime(2026, 1, 18, 11, 0, 0)

        result = recorder._save_to_spreadsheet(game, start_time, end_time)

        self.assertFalse(result)

    def test_save_includes_correct_values(self):
        """保存時に正しい値が含まれる."""
        handler = FakeLogHandler()
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)
        game = models.GameEntry(game_title="TestGame",
                                window_title="TestGame", play_with_friends=True)

        start_time = datetime(2026, 1, 18, 10, 0, 0)
        end_time = datetime(2026, 1, 18, 11, 0, 0)

        recorder._save_to_spreadsheet(game, start_time, end_time)

        record = handler.records[0]
        self.assertEqual(record['title'], 'TestGame')
        self.assertEqual(record['start_time'], '2026/01/18 10:00:00')
        self.assertEqual(record['end_time'], '2026/01/18 11:00:00')
        self.assertTrue(record['play_with_friends'])


class TestMessagesConstants(unittest.TestCase):
    """Messagesクラスの定数テスト."""

    def test_game_recorded_message_format(self):
        """GAME_RECORDEDメッセージのフォーマット."""
        message = main.Messages.GAME_RECORDED.format(game_title="TestGame")

        self.assertIn("TestGame", message)
        self.assertIn("記録", message)

    def test_game_too_short_message_format(self):
        """GAME_TOO_SHORTメッセージのフォーマット."""
        message = main.Messages.GAME_TOO_SHORT.format(
            game_title="TestGame", min_minutes=5)

        self.assertIn("TestGame", message)
        self.assertIn("5", message)

    def test_no_game_playing_message(self):
        """NO_GAME_PLAYINGメッセージの存在."""
        self.assertIsNotNone(main.Messages.NO_GAME_PLAYING)
        self.assertIsInstance(main.Messages.NO_GAME_PLAYING, str)


class TestGameStateTrackerIntegration(unittest.TestCase):
    """GameStateTrackerの統合テスト."""

    def test_initialization_with_dependencies(self):
        """依存関係を持って初期化できる."""
        from src.core.adapters import SessionRecorder
        from src.core.domain import DailyStatsTracker, GameStateTracker

        mock_recorder = MagicMock(spec=SessionRecorder)
        mock_daily_stats = MagicMock(spec=DailyStatsTracker)

        tracker = GameStateTracker(
            recorder=mock_recorder,
            daily_stats=mock_daily_stats,
            browsers=['Chrome', 'Firefox'],
            inactive_timeout_minutes=5
        )

        # 依存関係が設定されていることを確認
        self.assertEqual(tracker.recorder, mock_recorder)
        self.assertEqual(tracker.daily_stats, mock_daily_stats)
        self.assertEqual(tracker.browsers, ['Chrome', 'Firefox'])
        self.assertEqual(tracker.inactive_timeout_minutes, 5)
        self.assertEqual(tracker._normalized_browsers, ['chrome', 'firefox'])

    def test_normalize_scan_inputs(self):
        """scan入力の正規化が1箇所で行われる."""
        from src.core.adapters import SessionRecorder
        from src.core.domain import DailyStatsTracker, GameStateTracker

        mock_recorder = MagicMock(spec=SessionRecorder)
        mock_daily_stats = MagicMock(spec=DailyStatsTracker)
        tracker = GameStateTracker(
            recorder=mock_recorder,
            daily_stats=mock_daily_stats,
            browsers=['Google Chrome'],
            inactive_timeout_minutes=5
        )

        window_titles = ['PlayGo.gg – Play Go Online - Google Chrome']
        foreground_title = 'PLAYGO.GG - PLAY GO ONLINE - GOOGLE CHROME'
        normalized_titles, normalized_foreground = tracker._normalize_scan_inputs(
            window_titles, foreground_title
        )

        self.assertEqual(normalized_titles, [
                         'playgo.gg - play go online - google chrome'])
        self.assertEqual(normalized_foreground,
                         'playgo.gg - play go online - google chrome')

    def test_set_browsers_updates_normalized_cache(self):
        """set_browsers()で正規化キャッシュが同期更新される."""
        from src.core.adapters import SessionRecorder
        from src.core.domain import DailyStatsTracker, GameStateTracker

        mock_recorder = MagicMock(spec=SessionRecorder)
        mock_daily_stats = MagicMock(spec=DailyStatsTracker)
        tracker = GameStateTracker(
            recorder=mock_recorder,
            daily_stats=mock_daily_stats,
            browsers=['Chrome'],
            inactive_timeout_minutes=5
        )

        tracker.set_browsers(['Microsoft Edge', 'Google Chrome'])

        self.assertEqual(tracker.browsers, ['Microsoft Edge', 'Google Chrome'])
        self.assertEqual(tracker._normalized_browsers, [
                         'microsoft edge', 'google chrome'])

    def test_set_browsers_skips_empty_normalized_values(self):
        """set_browsers()は正規化後に空になる値をキャッシュから除外する."""
        from src.core.adapters import SessionRecorder
        from src.core.domain import DailyStatsTracker, GameStateTracker

        mock_recorder = MagicMock(spec=SessionRecorder)
        mock_daily_stats = MagicMock(spec=DailyStatsTracker)
        tracker = GameStateTracker(
            recorder=mock_recorder,
            daily_stats=mock_daily_stats,
            browsers=['Chrome'],
            inactive_timeout_minutes=5
        )

        tracker.set_browsers(['', '   ', 'Google Chrome'])

        self.assertEqual(tracker.browsers, ['', '   ', 'Google Chrome'])
        self.assertEqual(tracker._normalized_browsers, ['google chrome'])

    def test_browsers_property_returns_copy(self):
        """browsersプロパティの外部変更は内部状態に影響しない."""
        from src.core.adapters import SessionRecorder
        from src.core.domain import DailyStatsTracker, GameStateTracker

        mock_recorder = MagicMock(spec=SessionRecorder)
        mock_daily_stats = MagicMock(spec=DailyStatsTracker)
        tracker = GameStateTracker(
            recorder=mock_recorder,
            daily_stats=mock_daily_stats,
            browsers=['Chrome'],
            inactive_timeout_minutes=5
        )

        browsers = tracker.browsers
        browsers.append('Edge')

        self.assertEqual(tracker.browsers, ['Chrome'])
        self.assertEqual(tracker._normalized_browsers, ['chrome'])

    def test_scan_result_dataclass(self):
        """ScanResultデータクラスが正しく動作する."""
        from src.core.domain import ScanResult

        game1 = models.GameEntry(game_title="Test1", window_title="Test1")
        game2 = models.GameEntry(game_title="Test2", window_title="Test2")

        result = ScanResult(
            active_games=[game1],
            inactive_games=[game2],
            recorded_seconds=120.0
        )

        self.assertEqual(len(result.active_games), 1)
        self.assertEqual(len(result.inactive_games), 1)
        self.assertEqual(result.recorded_seconds, 120.0)
        self.assertEqual(result.active_games[0].game_title, "Test1")
        self.assertEqual(result.inactive_games[0].game_title, "Test2")

    def test_scan_with_no_games(self):
        """ゲームがない場合は空の結果を返す."""
        from src.core.adapters import SessionRecorder
        from src.core.domain import DailyStatsTracker, GameStateTracker

        mock_recorder = MagicMock(spec=SessionRecorder)
        mock_daily_stats = MagicMock(spec=DailyStatsTracker)

        tracker = GameStateTracker(
            recorder=mock_recorder,
            daily_stats=mock_daily_stats,
            browsers=['Chrome'],
            inactive_timeout_minutes=5
        )

        mock_callback = MagicMock(return_value={})

        result = tracker.scan(
            games=[],
            window_titles=[],
            foreground_title=None,
            load_today_game_minutes_callback=mock_callback
        )

        self.assertEqual(len(result.active_games), 0)
        self.assertEqual(len(result.inactive_games), 0)
        self.assertEqual(result.recorded_seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
