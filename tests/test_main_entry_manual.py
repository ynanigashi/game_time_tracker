# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportOptionalMemberAccess=false

from tests.helpers.main_test_imports import *  # noqa: F401,F403


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

class TestManualRecordSave(unittest.TestCase):
    def test_save_manual_record_persists_and_refreshes_today_stats(self):
        from src.core.models import GameEntry
        from src.ui.manual_record_dialog import ManualPlayRecord

        window = create_mock_main_window()
        window._update_today_totals = MagicMock(return_value=1800.0)
        window._update_today_games_list = MagicMock()
        window._update_overtime_alert = MagicMock()
        window._sync_overlay = MagicMock()
        window._set_status = MagicMock()

        end_time = stable_today_now()
        start_time = end_time - timedelta(minutes=30)
        record = ManualPlayRecord(
            game=GameEntry(game_title="NTE", window_title="NTE"),
            start_time=start_time,
            end_time=end_time,
        )

        result = window._save_manual_record(record)

        self.assertTrue(result)
        self.assertEqual(len(window.recorder.log_handler.records), 1)
        self.assertEqual(window.recorder.log_handler.records[0]["title"], "NTE")
        self.assertEqual(window.daily_stats.today_game_minutes_cache["NTE"], 30.0)
        self.assertEqual(window.daily_stats.today_completed_seconds, 1800.0)
        window._update_today_totals.assert_called_once()
        window._update_today_games_list.assert_called_once()
        window._update_overtime_alert.assert_called_once_with(1800.0)
        window._sync_overlay.assert_called_once()
        window._set_status.assert_called_once()

    def test_save_manual_record_returns_false_when_under_threshold(self):
        from src.core.models import GameEntry
        from src.ui.manual_record_dialog import ManualPlayRecord

        window = create_mock_main_window()
        window._set_status = MagicMock()

        end_time = datetime.now().replace(microsecond=0)
        start_time = end_time - timedelta(minutes=3)
        record = ManualPlayRecord(
            game=GameEntry(game_title="NTE", window_title="NTE"),
            start_time=start_time,
            end_time=end_time,
        )

        result = window._save_manual_record(record)

        self.assertFalse(result)
        self.assertEqual(window.recorder.log_handler.records, [])
        window._set_status.assert_called_once()
