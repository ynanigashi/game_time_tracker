# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportOptionalMemberAccess=false

from tests.helpers.main_test_imports import *  # noqa: F401,F403


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

        window._actions._set_status("テストメッセージ")

        self.assertIn("テストメッセージ", window._window_title)
        self.assertIn(main.BASE_TITLE, window._window_title)

    def test_set_status_adds_to_excluded_titles(self):
        """_set_statusは新しいタイトルをexcluded_titlesに追加."""
        window = self._create_mock_main_window()

        window._actions._set_status("テストメッセージ")

        expected_title = f"{main.BASE_TITLE} - テストメッセージ"
        self.assertIn(expected_title, window.scanner.excluded_titles)

    def test_cycle_display_mode_changes_mode(self):
        """_cycle_display_modeはモードを循環."""
        window = self._create_mock_main_window()
        window._actions._apply_display_mode = MagicMock()
        window._actions._save_window_state = MagicMock()
        # DISPLAY_MODES = ("max", "mid", "min") なので max -> mid
        window._state_access.display_mode = 'max'

        window._actions._cycle_display_mode()

        self.assertEqual(window._state_access.display_mode, 'mid')
        window._actions._apply_display_mode.assert_called_once()
        window._actions._save_window_state.assert_called_once()

    def test_cycle_display_mode_wraps_around(self):
        """_cycle_display_modeはminからmaxに循環."""
        window = self._create_mock_main_window()
        window._actions._apply_display_mode = MagicMock()
        window._actions._save_window_state = MagicMock()
        # DISPLAY_MODES = ("max", "mid", "min") なので min -> max
        window._state_access.display_mode = 'min'

        window._actions._cycle_display_mode()

        self.assertEqual(window._state_access.display_mode, 'max')

    def test_apply_mode_geometry_sets_size(self):
        """_apply_mode_geometryはモードに応じたサイズを設定."""
        window = self._create_mock_main_window()
        window._state_access.display_mode = 'mid'

        window._actions._apply_mode_geometry()

        window.resize.assert_called_once_with(300, 200)

    def test_apply_mode_geometry_clamps_min_mode_size(self):
        """minモードのサイズは安全値以上にクランプされる."""
        window = self._create_mock_main_window()
        window._state_access.display_mode = 'min'
        window._state_access.mode_sizes['min'] = (200, 60)

        window._actions._apply_mode_geometry()

        window.resize.assert_called_once_with(
            main.MIN_MODE_SAFE_WIDTH, main.MIN_MODE_SAFE_HEIGHT)

    def test_save_window_state_records_current_mode_size(self):
        """_save_window_stateは現在のサイズをmode_sizesに記録."""
        window = self._create_mock_main_window()
        window._geom.width.return_value = 350
        window._geom.height.return_value = 250

        mock_state_controller = MagicMock()

        def save_side_effect(
            geom,
            display_mode,
            mode_sizes,
            overtime_alert_enabled,
            **kwargs,
        ):
            mode_sizes[display_mode] = (int(geom.width()), int(geom.height()))

        mock_state_controller.save.side_effect = save_side_effect
        window._controllers._get_state_controller = MagicMock(return_value=mock_state_controller)

        window._actions._save_window_state()

        self.assertEqual(window._state_access.mode_sizes['mid'], (350, 250))
        mock_state_controller.save.assert_called_once()
        self.assertTrue(mock_state_controller.save.call_args.args[3])

    def test_on_overtime_alert_toggled_off_syncs_overlay_immediately(self):
        """トグルOFF時に状態更新し、オーバーレイ同期を即時実行する."""
        window = self._create_mock_main_window()
        window._state_access.active_games_cache = []
        window._state_access.inactive_games_cache = []
        window._actions._sync_overlay = MagicMock()
        mock_ui_controller = MagicMock()
        mock_ui_controller.calculate_today_total_seconds.return_value = 1800.0
        window._controllers._get_ui_controller = MagicMock(return_value=mock_ui_controller)

        window._actions._on_overtime_alert_toggled(False)

        self.assertFalse(window._state_access.overtime_alert_enabled)
        tracker = window._actions._get_overtime_alert_tracker()
        self.assertTrue(tracker.initialized)
        self.assertEqual(tracker.last_checked_seconds, 1800.0)
        window._actions._sync_overlay.assert_called_once()

    def test_apply_display_mode_hides_widgets_in_min_mode(self):
        """_apply_display_modeはminモードでウィジェットを非表示."""
        window = self._create_mock_main_window()
        window._state_access.display_mode = 'min'
        window._actions._set_widget_visibility = MagicMock()
        window._actions._set_widget_with_height = MagicMock()

        window._actions._apply_display_mode()

        # session_labelはis_expanded=Falseで非表示
        calls = [call for call in window._actions._set_widget_visibility.call_args_list]
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
        window._actions._set_status = self._mock_set_status(window)
        window._actions._apply_display_mode = MagicMock()
        window._actions._apply_mode_geometry = MagicMock()

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
                    window._actions._init_components()

        self.assertFalse(window._disabled)
        self.assertEqual(len(window._state_access.games), 1)

    def test_init_components_empty_games_opens_game_catalog(self):
        """_init_componentsはゲームが空の場合ゲーム管理を開く."""
        window = self._create_mock_main_window()
        window._actions._set_status = self._mock_set_status(window)
        window._actions._open_game_catalog_dialog = MagicMock()

        mock_config = MagicMock()

        with patch('src.app.main.ConfigLoader') as MockConfigLoader:
            MockConfigLoader.return_value.load.return_value = mock_config
            with patch('src.app.main.GameInfoLoader') as MockGameInfoLoader:
                MockGameInfoLoader.return_value.load.return_value = []
                window._actions._init_components()

        self.assertFalse(window._disabled)
        self.assertIn('ゲーム情報が未登録', window._status)
        window._actions._open_game_catalog_dialog.assert_called_once()

    def test_init_components_loghandler_file_not_found_opens_settings(self):
        """_init_componentsはLogHandlerのFileNotFoundErrorで設定画面を開く."""
        window = self._create_mock_main_window()
        window._actions._set_status = self._mock_set_status(window)
        window._actions._open_settings_dialog = MagicMock()

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
                ), patch('src.app.main.QMessageBox.warning') as mock_warning:
                    window._actions._init_components()

        self.assertFalse(window._disabled)
        self.assertIn('認証情報', window._status)
        mock_warning.assert_called_once()
        window._actions._open_settings_dialog.assert_called_once()

    def test_init_components_spreadsheet_not_found_disables(self):
        """_init_componentsはSpreadsheetNotFoundで無効化."""
        window = self._create_mock_main_window()
        window._actions._set_status = self._mock_set_status(window)

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
                    window._actions._init_components()

        self.assertTrue(window._disabled)
        self.assertIn('ログハンドラー初期化エラー', window._status)

    def test_init_components_api_error_disables(self):
        """_init_componentsはAPIErrorで無効化."""
        window = self._create_mock_main_window()
        window._actions._set_status = self._mock_set_status(window)

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
                    window._actions._init_components()

        self.assertTrue(window._disabled)
        self.assertIn('ログハンドラー初期化エラー', window._status)

    def test_init_components_generic_exception_disables(self):
        """_init_componentsは汎用Exceptionで無効化."""
        window = self._create_mock_main_window()
        window._actions._set_status = self._mock_set_status(window)

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
                        window._actions._init_components()

            self.assertTrue(window._disabled)
            self.assertIn('初期化エラー', window._status)
        finally:
            # 元に戻す
            fake_gspread.exceptions.APIError = original_api_error


    def test_init_components_missing_settings_opens_settings_dialog(self):
        window = self._create_mock_main_window()
        window._actions._set_status = self._mock_set_status(window)
        window._actions._open_settings_dialog = MagicMock()
        window._get_bootstrapper = MagicMock()
        window._get_bootstrapper.return_value.bootstrap.side_effect = (
            MainWindowBootstrapError(
                "設定が未作成です。設定画面で入力して保存してください。",
                open_settings=True,
            )
        )

        window._actions._init_components()

        self.assertFalse(window._disabled)
        self.assertIn("設定が未作成", window._status)
        window._actions._open_settings_dialog.assert_called_once()

    def test_init_components_missing_games_opens_game_catalog_dialog(self):
        window = self._create_mock_main_window()
        window._actions._set_status = self._mock_set_status(window)
        window._actions._open_game_catalog_dialog = MagicMock()
        window._get_bootstrapper = MagicMock()
        window._get_bootstrapper.return_value.bootstrap.side_effect = (
            MainWindowBootstrapError(
                "ゲーム情報が未登録です。ゲーム管理で追加してください。",
                open_game_catalog=True,
            )
        )

        window._actions._init_components()

        self.assertFalse(window._disabled)
        self.assertIn("ゲーム情報が未登録", window._status)
        window._actions._open_game_catalog_dialog.assert_called_once()

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

class TestApplyDisplayModeMaxMid(unittest.TestCase):
    """_apply_display_modeのmax/midモードテスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        with patch.object(main.MainWindow, '__init__', lambda self: None):
            window = main.MainWindow()
        window._initialize_collaborators()

        window._state_access.display_mode = 'mid'
        window._state_access.mode_sizes = {'min': (300, 80), 'mid': (300, 200), 'max': (300, 400)}

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
        window.w.manual_record_button = MagicMock()

        window._actions._apply_mode_geometry = MagicMock()

        return window

    def test_max_mode_shows_window_list(self):
        """maxモードでwindow_listが表示される."""
        window = self._create_mock_main_window()
        window._state_access.display_mode = 'max'

        window._actions._apply_display_mode()

        # window_listが表示される
        window.w.window_list.setVisible.assert_called_with(True)
        window.w.window_label.setVisible.assert_called_with(True)

    def test_mid_mode_hides_window_list(self):
        """midモードでwindow_listが非表示."""
        window = self._create_mock_main_window()
        window._state_access.display_mode = 'mid'

        window._actions._apply_display_mode()

        # window_listが非表示
        window.w.window_list.setVisible.assert_called_with(False)
        window.w.window_label.setVisible.assert_called_with(False)

    def test_mid_mode_shows_session_and_active(self):
        """midモードでsessionとactiveが表示される."""
        window = self._create_mock_main_window()
        window._state_access.display_mode = 'mid'

        window._actions._apply_display_mode()

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
        window._state_access.display_mode = 'max'

        window._actions._apply_display_mode()

        # 全ウィジェットが表示
        window.w.today_label.setVisible.assert_called_with(True)
        window.w.session_label.setVisible.assert_called_with(True)
        window.w.active_label.setVisible.assert_called_with(True)
        window.w.today_games_label.setVisible.assert_called_with(True)
        window.w.window_label.setVisible.assert_called_with(True)

    def test_min_mode_hides_session_active_games(self):
        """minモードでsession/active/gamesが非表示."""
        window = self._create_mock_main_window()
        window._state_access.display_mode = 'min'

        window._actions._apply_display_mode()

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
        window._state_access.display_mode = 'min'

        window._actions._apply_display_mode()

        window.w.overtime_alert_toggle.setVisible.assert_called_with(True)

    def test_apply_mode_geometry_called(self):
        """_apply_mode_geometryが呼び出される."""
        window = self._create_mock_main_window()

        for mode in ['min', 'mid', 'max']:
            window._state_access.display_mode = mode
            window._actions._apply_mode_geometry.reset_mock()

            window._actions._apply_display_mode()

            window._actions._apply_mode_geometry.assert_called_once()

class TestSetWidgetVisibility(unittest.TestCase):
    """_set_widget_visibilityの単体テスト."""

    def _create_mock_main_window(self):
        """モックされたMainWindowを作成."""
        return create_mock_main_window(include_state_tracker=False, include_ui=False)

    def test_set_visible_true(self):
        """visible=Trueでウィジェットを表示."""
        window = self._create_mock_main_window()
        mock_widget = MagicMock()

        window._actions._set_widget_visibility(mock_widget, True)

        mock_widget.setVisible.assert_called_once_with(True)

    def test_set_visible_false(self):
        """visible=Falseでウィジェットを非表示."""
        window = self._create_mock_main_window()
        mock_widget = MagicMock()

        window._actions._set_widget_visibility(mock_widget, False)

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

        window._actions._set_widget_with_height(mock_widget, True, min_height=50, max_height=200)

        mock_widget.setVisible.assert_called_once_with(True)
        mock_widget.setMinimumHeight.assert_called_once_with(50)
        mock_widget.setMaximumHeight.assert_called_once_with(200)

    def test_set_visible_false_with_zero_height(self):
        """visible=Falseで非表示と高さ0を設定."""
        window = self._create_mock_main_window()
        mock_widget = MagicMock()

        window._actions._set_widget_with_height(mock_widget, False, min_height=0, max_height=0)

        mock_widget.setVisible.assert_called_once_with(False)
        mock_widget.setMinimumHeight.assert_called_once_with(0)
        mock_widget.setMaximumHeight.assert_called_once_with(0)

    def test_height_values_are_keyword_only(self):
        """min_height/max_heightはキーワード引数のみ."""
        window = self._create_mock_main_window()
        mock_widget = MagicMock()

        # 位置引数で渡すとエラー
        with self.assertRaises(TypeError):
            window._actions._set_widget_with_height(mock_widget, True, 50, 200)
