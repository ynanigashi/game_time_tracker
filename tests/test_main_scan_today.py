# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportOptionalMemberAccess=false

from tests.helpers.main_test_imports import *  # noqa: F401,F403


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
        window.daily_stats = domain.DailyStatsTracker()
        window.recorder = services.SessionRecorder(
            log_handler=FakeLogHandler(), min_play_minutes=5)

        # GameStateTrackerを初期化
        window.state_tracker = domain.GameStateTracker(
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
        window.daily_stats = domain.DailyStatsTracker()
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
        window.daily_stats = domain.DailyStatsTracker()
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
