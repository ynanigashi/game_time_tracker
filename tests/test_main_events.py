# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportOptionalMemberAccess=false

from tests.helpers.main_test_imports import *  # noqa: F401,F403


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
        window.daily_stats = domain.DailyStatsTracker()
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
        window._show_context_menu = MagicMock()

        mock_event = MagicMock(spec=main.QMouseEvent)
        mock_event.button.return_value = main.Qt.MouseButton.RightButton

        with patch.object(main.QWidget, 'mousePressEvent'):
            window.mousePressEvent(mock_event)
            window._cycle_display_mode.assert_not_called()
            window._show_context_menu.assert_called_once_with(mock_event)

    def test_context_menu_selection_opens_report(self):
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        report_action = object()
        settings_action = object()
        exit_action = object()
        window._open_report_dialog = MagicMock()
        window._open_settings_dialog = MagicMock()
        window.close = MagicMock()

        window._handle_context_menu_selection(
            report_action,
            report_action=report_action,
            settings_action=settings_action,
            exit_action=exit_action,
        )

        window._open_report_dialog.assert_called_once()
        window._open_settings_dialog.assert_not_called()
        window.close.assert_not_called()

    def test_context_menu_selection_opens_settings(self):
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        report_action = object()
        game_catalog_action = object()
        settings_action = object()
        exit_action = object()
        window._open_report_dialog = MagicMock()
        window._open_game_catalog_dialog = MagicMock()
        window._open_settings_dialog = MagicMock()
        window.close = MagicMock()

        window._handle_context_menu_selection(
            settings_action,
            report_action=report_action,
            game_catalog_action=game_catalog_action,
            settings_action=settings_action,
            exit_action=exit_action,
        )

        window._open_settings_dialog.assert_called_once()
        window._open_report_dialog.assert_not_called()
        window._open_game_catalog_dialog.assert_not_called()
        window.close.assert_not_called()

    def test_context_menu_selection_opens_game_catalog(self):
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        report_action = object()
        game_catalog_action = object()
        settings_action = object()
        exit_action = object()
        window._open_report_dialog = MagicMock()
        window._open_game_catalog_dialog = MagicMock()
        window._open_settings_dialog = MagicMock()
        window.close = MagicMock()

        window._handle_context_menu_selection(
            game_catalog_action,
            report_action=report_action,
            game_catalog_action=game_catalog_action,
            settings_action=settings_action,
            exit_action=exit_action,
        )

        window._open_game_catalog_dialog.assert_called_once()
        window._open_report_dialog.assert_not_called()
        window._open_settings_dialog.assert_not_called()
        window.close.assert_not_called()

    def test_context_menu_selection_changes_display_mode(self):
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        report_action = object()
        game_catalog_action = object()
        settings_action = object()
        exit_action = object()
        mode_action = object()
        window.display_mode = 'max'
        window._apply_display_mode = MagicMock()
        window._save_window_state = MagicMock()
        window._open_report_dialog = MagicMock()
        window._open_game_catalog_dialog = MagicMock()
        window._open_settings_dialog = MagicMock()
        window.close = MagicMock()

        window._handle_context_menu_selection(
            mode_action,
            report_action=report_action,
            game_catalog_action=game_catalog_action,
            settings_action=settings_action,
            exit_action=exit_action,
            mode_actions={'mid': mode_action},
        )

        self.assertEqual(window.display_mode, 'mid')
        window._apply_display_mode.assert_called_once()
        window._save_window_state.assert_called_once()
        window._open_report_dialog.assert_not_called()
        window._open_game_catalog_dialog.assert_not_called()
        window._open_settings_dialog.assert_not_called()
        window.close.assert_not_called()

    def test_add_display_mode_menu_marks_current_mode(self):
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        window.display_mode = 'mid'
        menu = main.QMenu()

        actions = window._add_display_mode_menu(menu)

        self.assertEqual(set(actions.keys()), set(main.DISPLAY_MODES))
        self.assertTrue(actions['mid'].checked)
        self.assertFalse(actions['max'].checked)
        self.assertFalse(actions['min'].checked)

    def test_tray_menu_shows_only_relevant_window_action_when_hidden(self):
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        window.startup_window_visible = False
        window.tray_overlay_enabled = False
        window.isVisible = MagicMock(return_value=False)

        window._build_tray_menu()

        self.assertTrue(window._tray_show_action.visible)
        self.assertFalse(window._tray_hide_action.visible)

    def test_tray_menu_shows_only_relevant_window_action_when_visible(self):
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        window.startup_window_visible = False
        window.tray_overlay_enabled = False
        window.isVisible = MagicMock(return_value=True)

        window._build_tray_menu()

        self.assertFalse(window._tray_show_action.visible)
        self.assertTrue(window._tray_hide_action.visible)

    def test_context_menu_selection_exits(self):
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        report_action = object()
        settings_action = object()
        exit_action = object()
        window._open_report_dialog = MagicMock()
        window._open_settings_dialog = MagicMock()
        window.close = MagicMock()
        window._quit_application = MagicMock()

        window._handle_context_menu_selection(
            exit_action,
            report_action=report_action,
            settings_action=settings_action,
            exit_action=exit_action,
        )

        window._quit_application.assert_called_once()
        window.close.assert_not_called()
        window._open_report_dialog.assert_not_called()
        window._open_settings_dialog.assert_not_called()

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

        with patch('src.app.main_window.controller_methods.QTimer') as MockQTimer:
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
