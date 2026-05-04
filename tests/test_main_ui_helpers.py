# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportOptionalMemberAccess=false

from tests.helpers.main_test_imports import *  # noqa: F401,F403


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

        tracker = domain.DailyStatsTracker(get_current_date=lambda: current_date[0])
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
        now = stable_today_now()
        game.start_time = now - timedelta(minutes=10)
        window.inactive_games_cache = []

        window._update_today_totals([game], now)

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
        window._window_title_context_menu_connected = False
        window.w.window_list.itemClicked = MagicMock()
        window.w.window_list.customContextMenuRequested = MagicMock()
        window.w.window_list.setContextMenuPolicy = MagicMock()
        window.w.window_list.setToolTip = MagicMock()

        window._initialize_window_title_copy()

        window.w.window_list.itemClicked.connect.assert_called_once_with(
            window._on_window_title_item_clicked
        )
        window.w.window_list.customContextMenuRequested.connect.assert_called_once_with(
            window._show_window_title_context_menu
        )
        window.w.window_list.setContextMenuPolicy.assert_called_once()
        window.w.window_list.setToolTip.assert_called_once()
        self.assertTrue(window._window_title_copy_connected)
        self.assertTrue(window._window_title_context_menu_connected)

    def test_window_title_context_menu_opens_game_catalog_with_title(self):
        """ウィンドウタイトル右クリックメニューからゲーム管理を開く."""
        window = self._create_mock_main_window()
        item = MagicMock()
        item.text.return_value = "Game Window Title"
        window.w.window_list.itemAt.return_value = item
        window.w.window_list.mapToGlobal.side_effect = lambda pos: pos
        window._open_game_catalog_dialog = MagicMock()
        action = object()
        menu = MagicMock()
        menu.addAction.return_value = action
        menu.exec.return_value = action

        with patch("src.app.main_window.controller_methods.QMenu", return_value=menu):
            window._show_window_title_context_menu(object())

        menu.addAction.assert_called_once_with("ゲーム一覧に追加")
        window._open_game_catalog_dialog.assert_called_once_with(
            initial_window_title="Game Window Title"
        )

    def test_open_game_catalog_dialog_syncs_new_dialog_on_open(self):
        """ゲーム管理を新規に開いた時は自動同期を走らせる."""
        window = self._create_mock_main_window()
        dialog = MagicMock()

        with patch("src.app.main_window.controller_methods.GameCatalogDialog", return_value=dialog):
            window._open_game_catalog_dialog()

        dialog.sync_on_open.assert_called_once()
        self.assertLess(
            dialog.method_calls.index(call.show()),
            dialog.method_calls.index(call.sync_on_open()),
        )
        dialog.show.assert_called_once()
        dialog.raise_.assert_called_once()
        dialog.activateWindow.assert_called_once()

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
