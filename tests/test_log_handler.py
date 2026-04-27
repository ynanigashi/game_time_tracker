# pyright: reportAttributeAccessIssue=false, reportArgumentType=false,
# reportCallIssue=false
"""log_handler.py / gspread_service.py のユニットテスト."""

from src.core import services
from src.core import models
from src.infra.gspread_service import GspreadService
from src.infra.log_handler import LogHandler
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

# 共通スタブをインストール
from tests.test_stubs import install_stubs, fake_gspread, FakeLogHandler
install_stubs()


class TestLogHandlerLocalPrimary(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _store(self):
        from src.infra.play_log_store import PlayLogStore

        return PlayLogStore(Path(self.temp_dir.name) / "play_logs.sqlite3")

    def _config(self):
        from src.infra.config_loader import LogHandlerConfig

        return LogHandlerConfig(cert_file_path="service_account.json", sheet_key="key")

    def _local_only_config(self):
        from src.infra.config_loader import LogHandlerConfig

        return LogHandlerConfig(
            cert_file_path="service_account.json",
            sheet_key="",
            backup_mode="local_only",
        )

    def test_imports_spreadsheet_records_when_local_db_empty(self):
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.return_value = [
            {
                "index": 1,
                "start_time": "2026/04/26 10:00:00",
                "end_time": "2026/04/26 10:30:00",
                "title": "Game",
                "play_with_friends": "TRUE",
            }
        ]
        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            handler = LogHandler(self._config(), play_log_store=self._store())

        self.assertEqual(len(handler.records), 1)
        self.assertEqual(handler.index, 1)
        self.assertEqual(handler.records[0]["title"], "Game")

    def test_save_record_succeeds_when_spreadsheet_backup_fails(self):
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.return_value = []
        spreadsheet.append_row.return_value = False
        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            handler = LogHandler(self._config(), play_log_store=self._store())

        result = handler.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Game", False]
        )

        self.assertTrue(result)
        self.assertEqual(len(handler.records), 1)
        spreadsheet.append_row.assert_called_once()

    def test_startup_backs_up_pending_local_records(self):
        store = self._store()
        store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Game", False],
            backed_up=False,
        )
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.return_value = []
        spreadsheet.append_row.return_value = True

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            handler = LogHandler(self._config(), play_log_store=store)

        self.assertEqual(spreadsheet.get_all_records.call_count, 1)
        args = spreadsheet.append_row.call_args.args[0]
        self.assertEqual(
            args[2:],
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Game", False],
        )
        self.assertEqual(handler.records[0]["title"], "Game")
        self.assertEqual(store.load_pending_backup_records(), [])

    def test_fetch_failure_keeps_pending_records_for_later_retry(self):
        store = self._store()
        store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Game", False],
            backed_up=False,
        )
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.side_effect = RuntimeError("network error")

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            LogHandler(self._config(), play_log_store=store)

        spreadsheet.append_row.assert_not_called()
        self.assertEqual(len(store.load_pending_backup_records()), 1)

    def test_spreadsheet_sync_imports_remote_records_even_when_local_has_data(self):
        store = self._store()
        store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Local", False],
            backed_up=True,
        )
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.return_value = [
            {
                "record_id": "remote-1",
                "device_id": "pc-2",
                "index": 1,
                "start_time": "2026/04/26 11:00:00",
                "end_time": "2026/04/26 11:30:00",
                "title": "Remote",
                "play_with_friends": "FALSE",
            }
        ]
        spreadsheet.append_row.return_value = True

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            handler = LogHandler(self._config(), play_log_store=store)

        titles = [record["title"] for record in handler.records]
        self.assertEqual(titles, ["Local", "Remote"])

    def test_manual_sync_with_spreadsheet_updates_cache_and_returns_counts(self):
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.side_effect = [
            [],
            [
                {
                    "record_id": "remote-1",
                    "device_id": "pc-2",
                    "index": 1,
                    "start_time": "2026/04/26 11:00:00",
                    "end_time": "2026/04/26 11:30:00",
                    "title": "Remote",
                    "play_with_friends": "FALSE",
                }
            ],
        ]

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            handler = LogHandler(self._config(), play_log_store=self._store())
            result = handler.sync_with_spreadsheet()

        self.assertEqual(result.imported, 1)
        self.assertEqual(result.backed_up, 0)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.remote_count, 1)
        self.assertEqual(result.import_skipped, 0)
        self.assertEqual(result.pending_count, 0)
        self.assertEqual(handler.records[0]["title"], "Remote")

    def test_manual_sync_result_counts_invalid_remote_rows(self):
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.side_effect = [
            [],
            [
                {
                    "record_id": "remote-1",
                    "device_id": "pc-2",
                    "index": 1,
                    "start_time": "2026/04/26 11:00:00",
                    "end_time": "2026/04/26 11:30:00",
                    "title": "Remote",
                    "play_with_friends": "FALSE",
                },
                {"record_id": "bad-row", "index": ""},
            ],
        ]

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            handler = LogHandler(self._config(), play_log_store=self._store())
            result = handler.sync_with_spreadsheet()

        self.assertEqual(result.remote_count, 2)
        self.assertEqual(result.imported, 1)
        self.assertEqual(result.import_skipped, 1)
        self.assertEqual(result.total, 1)

    def test_manual_sync_result_reports_fetch_error_and_pending_count(self):
        store = self._store()
        store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Game", False],
            backed_up=False,
        )
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.side_effect = RuntimeError("network error")

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            handler = LogHandler(self._config(), play_log_store=store)
            result = handler.sync_with_spreadsheet()

        self.assertEqual(result.remote_count, 0)
        self.assertEqual(result.pending_count, 1)
        self.assertEqual(result.backup_failed, 1)
        self.assertIn("network error", result.error_message)

    def test_duplicate_record_id_overwrites_spreadsheet_row_by_default(self):
        store = self._store()
        saved = store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Local", False],
            backed_up=False,
        )
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.return_value = [
            {
                "record_id": saved["record_id"],
                "device_id": "pc-2",
                "index": 1,
                "start_time": "2026/04/26 09:00:00",
                "end_time": "2026/04/26 09:30:00",
                "title": "Remote",
                "play_with_friends": "FALSE",
            }
        ]
        spreadsheet.update_row_by_record_id.return_value = True

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            LogHandler(self._config(), play_log_store=store)

        spreadsheet.update_row_by_record_id.assert_called_once()
        spreadsheet.append_row.assert_not_called()
        self.assertEqual(store.load_pending_backup_records(), [])

    def test_duplicate_record_id_can_be_reissued_before_append(self):
        from src.infra.config_loader import LogHandlerConfig

        store = self._store()
        saved = store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Local", False],
            backed_up=False,
        )
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.return_value = [
            {
                "record_id": saved["record_id"],
                "device_id": "pc-2",
                "index": 1,
                "start_time": "2026/04/26 09:00:00",
                "end_time": "2026/04/26 09:30:00",
                "title": "Remote",
                "play_with_friends": "FALSE",
            }
        ]
        spreadsheet.append_row.return_value = True
        config = LogHandlerConfig(
            cert_file_path="service_account.json",
            sheet_key="key",
            sync_conflict_policy="new_id",
        )

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            LogHandler(config, play_log_store=store)

        appended = spreadsheet.append_row.call_args.args[0]
        self.assertNotEqual(appended[0], saved["record_id"])
        spreadsheet.update_row_by_record_id.assert_not_called()
        self.assertEqual(store.load_pending_backup_records(), [])

    def test_pending_backup_uses_legacy_values_for_legacy_sheet_headers(self):
        store = self._store()
        store.save_record(
            [3, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Legacy", True],
            backed_up=False,
        )
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.return_value = [
            {
                "No": 1,
                "start_time": "2026/04/26 09:00:00",
                "end_time": "2026/04/26 09:30:00",
                "title": "Remote",
                "with_friends": "FALSE",
            }
        ]
        spreadsheet.append_row.return_value = True

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            LogHandler(self._config(), play_log_store=store)

        spreadsheet.append_row.assert_called_once_with(
            [3, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Legacy", True]
        )
        self.assertEqual(store.load_pending_backup_records(), [])

    def test_log_sheet_gid_is_passed_to_gspread_service(self):
        from src.infra.config_loader import LogHandlerConfig

        config = LogHandlerConfig(
            cert_file_path="service_account.json",
            sheet_key="key",
            sheet_gid=123,
        )
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.return_value = []
        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet) as service:
            LogHandler(config, play_log_store=self._store())

        service.assert_called_once_with(
            cert_file_path="service_account.json",
            sheet_key="key",
            sheet_gid=123,
        )

    def test_local_only_mode_does_not_connect_spreadsheet_backup(self):
        store = self._store()
        with patch("src.infra.log_handler.GspreadService") as service:
            handler = LogHandler(self._local_only_config(), play_log_store=store)

        service.assert_not_called()
        self.assertIsNone(handler.gspread_service)
        self.assertEqual(handler.records, [])

    def test_update_record_updates_local_cache_and_spreadsheet_row(self):
        store = self._store()
        saved = store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Game", True],
            backed_up=True,
        )
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.side_effect = [
            [],
            [
                {
                    "record_id": saved["record_id"],
                    "device_id": saved["device_id"],
                    "index": 1,
                    "start_time": "2026/04/26 10:00:00",
                    "end_time": "2026/04/26 10:30:00",
                    "title": "Game",
                    "play_with_friends": "TRUE",
                }
            ],
        ]
        spreadsheet.update_row_by_record_id.return_value = True

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            handler = LogHandler(self._config(), play_log_store=store)
            result = handler.update_record(
                saved["record_id"],
                [
                    1,
                    "2026/04/26 11:00:00",
                    "2026/04/26 12:00:00",
                    "Edited",
                    False,
                ],
            )

        self.assertTrue(result.local_updated)
        self.assertTrue(result.spreadsheet_updated)
        self.assertEqual(handler.records[0]["title"], "Edited")
        spreadsheet.update_row_by_record_id.assert_called_once_with(
            saved["record_id"],
            [
                saved["record_id"],
                saved["device_id"],
                1,
                "2026/04/26 11:00:00",
                "2026/04/26 12:00:00",
                "Edited",
                False,
            ],
        )
        spreadsheet.append_row.assert_not_called()
        self.assertEqual(store.load_pending_backup_records(), [])

    def test_pending_edited_record_overwrites_even_with_new_id_policy(self):
        from src.infra.config_loader import LogHandlerConfig

        store = self._store()
        saved = store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Game", True],
            backed_up=True,
        )
        store.update_record(
            saved["record_id"],
            [1, "2026/04/26 11:00:00", "2026/04/26 12:00:00", "Edited", False],
        )
        spreadsheet = MagicMock()
        spreadsheet.get_all_records.return_value = [
            {
                "record_id": saved["record_id"],
                "device_id": saved["device_id"],
                "index": 1,
                "start_time": "2026/04/26 10:00:00",
                "end_time": "2026/04/26 10:30:00",
                "title": "Game",
                "play_with_friends": "TRUE",
            }
        ]
        spreadsheet.update_row_by_record_id.return_value = True
        config = LogHandlerConfig(
            cert_file_path="service_account.json",
            sheet_key="key",
            sync_conflict_policy="new_id",
        )

        with patch("src.infra.log_handler.GspreadService", return_value=spreadsheet):
            LogHandler(config, play_log_store=store)

        spreadsheet.update_row_by_record_id.assert_called_once()
        spreadsheet.append_row.assert_not_called()
        self.assertEqual(store.load_pending_backup_records(), [])


class TestLogHandlerCache(unittest.TestCase):
    """LogHandlerのキャッシュ機能テスト."""

    def test_save_record_updates_cache(self):
        """save_record後にget_cached_recordsで新しいレコードが取得できる."""
        handler = FakeLogHandler()

        # 初期状態は空
        self.assertEqual(len(handler.get_cached_records()), 0)

        # レコードを保存
        handler.save_record([
            1,
            "2026/01/18 10:00:00",
            "2026/01/18 11:00:00",
            "TestGame",
            False,
        ])

        # キャッシュに追加されている
        cached = handler.get_cached_records()
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0]['title'], "TestGame")
        self.assertEqual(cached[0]['start_time'], "2026/01/18 10:00:00")
        self.assertEqual(cached[0]['end_time'], "2026/01/18 11:00:00")

    def test_multiple_saves_accumulate_in_cache(self):
        """複数回のsave_recordでキャッシュに蓄積される."""
        handler = FakeLogHandler()

        handler.save_record(
            [1, "2026/01/18 10:00:00", "2026/01/18 11:00:00", "Game1", False])
        handler.save_record(
            [2, "2026/01/18 12:00:00", "2026/01/18 13:00:00", "Game2", True])
        handler.save_record(
            [3, "2026/01/18 14:00:00", "2026/01/18 15:00:00", "Game1", False])

        cached = handler.get_cached_records()
        self.assertEqual(len(cached), 3)
        self.assertEqual(cached[0]['title'], "Game1")
        self.assertEqual(cached[1]['title'], "Game2")
        self.assertEqual(cached[2]['title'], "Game1")

    def test_cache_can_filter_by_date(self):
        """キャッシュから特定日付のレコードをフィルタできる."""
        handler = FakeLogHandler()

        # 異なる日付のレコードを追加
        handler.save_record(
            [1, "2026/01/17 10:00:00", "2026/01/17 11:00:00", "Yesterday", False])
        handler.save_record(
            [2, "2026/01/18 10:00:00", "2026/01/18 11:00:00", "Today1", False])
        handler.save_record(
            [3, "2026/01/18 14:00:00", "2026/01/18 15:00:00", "Today2", False])

        # 今日のレコードだけをフィルタ
        today_str = "2026/01/18"
        today_records = [
            r for r in handler.get_cached_records()
            if r['start_time'].startswith(today_str)
        ]

        self.assertEqual(len(today_records), 2)
        self.assertEqual(today_records[0]['title'], "Today1")
        self.assertEqual(today_records[1]['title'], "Today2")

    def test_cache_calculates_play_minutes_correctly(self):
        """キャッシュからプレイ時間（分）を正しく計算できる."""
        handler = FakeLogHandler()

        # 30分と60分のレコード
        handler.save_record(
            [1, "2026/01/18 10:00:00", "2026/01/18 10:30:00", "Game1", False])
        handler.save_record(
            [2, "2026/01/18 12:00:00", "2026/01/18 13:00:00", "Game2", False])
        handler.save_record(
            [3, "2026/01/18 14:00:00", "2026/01/18 14:45:00", "Game1", False])

        # ゲームごとの合計時間を計算
        game_minutes = {}
        for record in handler.get_cached_records():
            start = datetime.strptime(record['start_time'], "%Y/%m/%d %H:%M:%S")
            end = datetime.strptime(record['end_time'], "%Y/%m/%d %H:%M:%S")
            minutes = (end - start).total_seconds() / 60
            title = record['title']
            game_minutes[title] = game_minutes.get(title, 0) + minutes

        self.assertEqual(game_minutes['Game1'], 75)  # 30 + 45
        self.assertEqual(game_minutes['Game2'], 60)


class TestFakeLogHandlerSaveFailure(unittest.TestCase):
    """LogHandler.save_record()の失敗テスト."""

    def test_save_record_returns_false_on_failure(self):
        """保存失敗時はFalseを返す."""
        class FailingLogHandler(FakeLogHandler):
            def save_record(self, values):
                return False

        handler = FailingLogHandler()
        recorder = services.SessionRecorder(log_handler=handler, min_play_minutes=5)

        game = models.GameEntry(
            game_title="TestGame",
            window_title="TestGame",
            is_playing=True,
        )
        game.start_time = datetime.now() - timedelta(minutes=10)

        # save_recordが失敗するとNoneが返る
        result = recorder.record(game)

        # any_saved = Falseなのでresultはなし
        self.assertIsNone(result)


class TestLogHandlerSaveRecordExceptions(unittest.TestCase):
    """LogHandler.save_record()の例外ハンドリングテスト."""

    def test_api_error_returns_false(self):
        """APIError発生時はFalseを返す."""
        class MockLogHandler:
            def __init__(self):
                self.records = []
                self.index = 0
                self.sheet = MagicMock()
                mock_response = MagicMock()
                mock_response.text = "Quota exceeded"
                mock_response.json.return_value = {}
                self.sheet.append_row.side_effect = fake_gspread.exceptions.APIError(
                    mock_response
                )

            def save_record(self, values):
                try:
                    self.sheet.append_row(values, value_input_option='USER_ENTERED')
                    return True
                except fake_gspread.exceptions.APIError as e:
                    print(f'APIError occurred while appending row: {e}')
                    return False
                except Exception as e:
                    print(f'Exception occurred while appending row: {e}')
                    return False

        handler = MockLogHandler()
        result = handler.save_record(
            [1, '2026/01/18 10:00:00', '2026/01/18 11:00:00', 'Test', False])

        self.assertFalse(result)

    def test_generic_exception_returns_false(self):
        """汎用Exception発生時はFalseを返す."""
        class MockLogHandler:
            def __init__(self):
                self.records = []
                self.index = 0
                self.sheet = MagicMock()
                self.sheet.append_row.side_effect = RuntimeError("Network error")

            def save_record(self, values):
                try:
                    self.sheet.append_row(values, value_input_option='USER_ENTERED')
                    return True
                except fake_gspread.exceptions.APIError as e:
                    print(f'APIError occurred while appending row: {e}')
                    return False
                except Exception as e:
                    print(f'Exception occurred while appending row: {e}')
                    return False

        handler = MockLogHandler()
        result = handler.save_record(
            [1, '2026/01/18 10:00:00', '2026/01/18 11:00:00', 'Test', False])

        self.assertFalse(result)

    def test_success_returns_true_and_updates_cache(self):
        """成功時はTrueを返しキャッシュも更新."""
        class MockLogHandler:
            def __init__(self):
                self.records = []
                self.index = 0
                self.sheet = MagicMock()

            def save_record(self, values):
                try:
                    self.sheet.append_row(values, value_input_option='USER_ENTERED')
                    if len(values) >= 5:
                        self.records.append({
                            'index': values[0],
                            'start_time': values[1],
                            'end_time': values[2],
                            'title': values[3],
                            'play_with_friends': values[4],
                        })
                    return True
                except Exception:
                    return False

        handler = MockLogHandler()
        result = handler.save_record(
            [1, '2026/01/18 10:00:00', '2026/01/18 11:00:00', 'Test', False])

        self.assertTrue(result)
        self.assertEqual(len(handler.records), 1)
        self.assertEqual(handler.records[0]['title'], 'Test')


class TestLogHandlerFormatDatetime(unittest.TestCase):
    """LogHandler.format_datetime_to_gss_styleのテスト."""

    def test_formats_datetime_correctly(self):
        """日時を正しいフォーマットに変換."""
        handler = FakeLogHandler()
        dt = datetime(2026, 1, 18, 14, 30, 45)

        result = handler.format_datetime_to_gss_style(dt)

        self.assertEqual(result, '2026/01/18 14:30:45')

    def test_formats_midnight(self):
        """深夜0時を正しくフォーマット."""
        handler = FakeLogHandler()
        dt = datetime(2026, 1, 18, 0, 0, 0)

        result = handler.format_datetime_to_gss_style(dt)

        self.assertEqual(result, '2026/01/18 00:00:00')

    def test_formats_end_of_day(self):
        """23:59:59を正しくフォーマット."""
        handler = FakeLogHandler()
        dt = datetime(2026, 1, 18, 23, 59, 59)

        result = handler.format_datetime_to_gss_style(dt)

        self.assertEqual(result, '2026/01/18 23:59:59')


class TestLogHandlerGetAndIncrementIndex(unittest.TestCase):
    """LogHandler.get_and_increment_indexのテスト."""

    def test_increments_index_each_call(self):
        """呼び出すごとにインデックスが増加."""
        handler = FakeLogHandler()
        handler.current_index = 5

        idx1 = handler.get_and_increment_index()
        idx2 = handler.get_and_increment_index()
        idx3 = handler.get_and_increment_index()

        self.assertEqual(idx1, 6)
        self.assertEqual(idx2, 7)
        self.assertEqual(idx3, 8)

    def test_starts_from_record_count(self):
        """初期インデックスはレコード数."""
        handler = FakeLogHandler()
        # 3件のレコードがある状態をシミュレート
        handler.records = [{'index': 1}, {'index': 2}, {'index': 3}]
        handler.current_index = 3

        idx = handler.get_and_increment_index()

        self.assertEqual(idx, 4)


class TestGspreadService(unittest.TestCase):
    """GspreadServiceのテスト."""

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_init_stores_credentials(self, mock_sa):
        """初期化時に認証情報とシートキーを保存."""
        from src.infra.gspread_service import GspreadService

        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_gc.open_by_key.return_value.sheet1 = mock_sheet
        mock_sa.return_value = mock_gc

        service = GspreadService(cert_file_path='test.json', sheet_key='test_key')

        self.assertEqual(service.cert_file_path, 'test.json')
        self.assertEqual(service.sheet_key, 'test_key')

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_connect_success(self, mock_sa):
        """_connect()が正常に接続する."""
        from src.infra.gspread_service import GspreadService

        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_gc.open_by_key.return_value.sheet1 = mock_sheet
        mock_sa.return_value = mock_gc

        service = GspreadService(cert_file_path='test.json', sheet_key='test_key')

        # __init__で_connect()が呼ばれる
        mock_sa.assert_called_with(filename=Path('test.json'))
        mock_gc.open_by_key.assert_called_with('test_key')
        self.assertIsNotNone(service.sheet)

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_get_all_records_calls_connect(self, mock_sa):
        """get_all_records()が_connect()を呼び出す."""
        from src.infra.gspread_service import GspreadService

        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_sheet.get_all_records.return_value = [{'game': 'Test'}]
        mock_gc.open_by_key.return_value.sheet1 = mock_sheet
        mock_sa.return_value = mock_gc

        service = GspreadService(cert_file_path='test.json', sheet_key='test_key')
        result = service.get_all_records()

        self.assertEqual(result, [{'game': 'Test'}])
        mock_sheet.get_all_records.assert_called_once()

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_append_row_success_returns_true(self, mock_sa):
        """append_row()が成功時にTrueを返す."""
        from src.infra.gspread_service import GspreadService

        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_gc.open_by_key.return_value.sheet1 = mock_sheet
        mock_sa.return_value = mock_gc

        service = GspreadService(cert_file_path='test.json', sheet_key='test_key')
        result = service.append_row(['value1', 'value2'])

        self.assertTrue(result)
        mock_sheet.append_row.assert_called_once_with(
            ['value1', 'value2'], value_input_option='USER_ENTERED')

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_append_row_api_error_returns_false(self, mock_sa):
        """append_row()がAPIErrorで失敗時にFalseを返す."""
        from src.infra.gspread_service import GspreadService

        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Quota exceeded"
        mock_response.json.return_value = {}
        mock_sheet.append_row.side_effect = fake_gspread.exceptions.APIError(
            mock_response
        )
        mock_gc.open_by_key.return_value.sheet1 = mock_sheet
        mock_sa.return_value = mock_gc

        service = GspreadService(cert_file_path='test.json', sheet_key='test_key')
        result = service.append_row(['value1', 'value2'])

        self.assertFalse(result)

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_append_row_generic_exception_returns_false(self, mock_sa):
        """append_row()が一般例外で失敗時にFalseを返す."""
        from src.infra.gspread_service import GspreadService

        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_sheet.append_row.side_effect = Exception("Network error")
        mock_gc.open_by_key.return_value.sheet1 = mock_sheet
        mock_sa.return_value = mock_gc

        service = GspreadService(cert_file_path='test.json', sheet_key='test_key')
        result = service.append_row(['value1', 'value2'])

        self.assertFalse(result)

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_update_row_by_record_id_updates_matching_row(self, mock_sa):
        """record_idが一致する行を更新する."""
        from src.infra.gspread_service import GspreadService

        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = [
            ["record_id", "device_id", "index"],
            ["record-1", "pc", "1"],
        ]
        mock_gc.open_by_key.return_value.sheet1 = mock_sheet
        mock_sa.return_value = mock_gc

        service = GspreadService(cert_file_path='test.json', sheet_key='test_key')
        result = service.update_row_by_record_id("record-1", ["record-1", "pc", 1])

        self.assertTrue(result)
        mock_sheet.update.assert_called_once_with(
            range_name="A2:C2",
            values=[["record-1", "pc", 1]],
            value_input_option="USER_ENTERED",
        )

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_update_row_by_key_updates_matching_row(self, mock_sa):
        """任意のキー列が一致する行を更新する."""
        from src.infra.gspread_service import GspreadService

        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = [
            ["id", "game_title", "window_title"],
            ["game-1", "Old", "Old Window"],
        ]
        mock_gc.open_by_key.return_value.sheet1 = mock_sheet
        mock_sa.return_value = mock_gc

        service = GspreadService(cert_file_path='test.json', sheet_key='test_key')
        result = service.update_row_by_key(
            "id",
            "game-1",
            ["game-1", "New", "New Window"],
        )

        self.assertTrue(result)
        mock_sheet.update.assert_called_once_with(
            range_name="A2:C2",
            values=[["game-1", "New", "New Window"]],
            value_input_option="USER_ENTERED",
        )

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_update_row_by_record_id_returns_false_when_missing(self, mock_sa):
        """record_id列または一致行がない場合はFalseを返す."""
        from src.infra.gspread_service import GspreadService

        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = [["index"], ["1"]]
        mock_gc.open_by_key.return_value.sheet1 = mock_sheet
        mock_sa.return_value = mock_gc

        service = GspreadService(cert_file_path='test.json', sheet_key='test_key')
        result = service.update_row_by_record_id("record-1", ["record-1"])

        self.assertFalse(result)
        mock_sheet.update.assert_not_called()


class TestLogHandlerGetTodayStats(unittest.TestCase):
    """ログハンドラーget_today_stats()のテスト."""

    def test_get_today_stats_normal_records(self):
        """正常なレコードから統計を正しく集計."""
        from src.infra.log_handler import LogHandler
        from datetime import datetime

        today = datetime.now().date()
        today_str = today.strftime('%Y/%m/%d')

        fake_handler = FakeLogHandler()
        fake_handler.records = [
            {
                'title': 'Game1',
                'start_time': f'{today_str} 10:00:00',
                'end_time': f'{today_str} 10:30:00',  # 30分
            },
            {
                'title': 'Game1',
                'start_time': f'{today_str} 11:00:00',
                'end_time': f'{today_str} 11:15:00',  # 15分
            },
            {
                'title': 'Game2',
                'start_time': f'{today_str} 12:00:00',
                'end_time': f'{today_str} 13:00:00',  # 60分
            },
        ]

        game_minutes, total_seconds = fake_handler.get_today_stats()

        # Game1: 30 + 15 = 45分, Game2: 60分
        self.assertAlmostEqual(game_minutes['Game1'], 45.0, places=1)
        self.assertAlmostEqual(game_minutes['Game2'], 60.0, places=1)
        # 合計: 105分 = 6300秒
        self.assertAlmostEqual(total_seconds, 6300.0, places=1)

    def test_get_today_stats_filters_other_days(self):
        """他の日のレコードを除外."""
        from datetime import datetime, timedelta

        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        today_str = today.strftime('%Y/%m/%d')
        yesterday_str = yesterday.strftime('%Y/%m/%d')

        fake_handler = FakeLogHandler()
        fake_handler.records = [
            {
                'title': 'Game1',
                'start_time': f'{today_str} 10:00:00',
                'end_time': f'{today_str} 10:30:00',  # 30分 - 今日
            },
            {
                'title': 'Game2',
                'start_time': f'{yesterday_str} 10:00:00',
                'end_time': f'{yesterday_str} 11:00:00',  # 60分 - 昨日（除外）
            },
        ]

        game_minutes, total_seconds = fake_handler.get_today_stats()

        # 今日のみ
        self.assertAlmostEqual(game_minutes.get('Game1', 0), 30.0, places=1)
        self.assertNotIn('Game2', game_minutes)
        self.assertAlmostEqual(total_seconds, 1800.0, places=1)  # 30分 = 1800秒

    def test_get_today_stats_handles_invalid_records(self):
        """不正なレコードが混入しても続行."""
        from datetime import datetime

        today = datetime.now().date()
        today_str = today.strftime('%Y/%m/%d')

        fake_handler = FakeLogHandler()
        fake_handler.records = [
            {
                'title': 'Game1',
                'start_time': f'{today_str} 10:00:00',
                'end_time': f'{today_str} 10:30:00',  # 正常
            },
            {
                'title': 'InvalidGame',
                'start_time': 'invalid_date',
                'end_time': f'{today_str} 11:00:00',  # 不正
            },
            {
                'title': 'Game2',
                # start_time欠落
                'end_time': f'{today_str} 12:00:00',
            },
            {
                'title': 'Game3',
                'start_time': f'{today_str} 13:00:00',
                'end_time': f'{today_str} 13:20:00',  # 正常
            },
        ]

        game_minutes, total_seconds = fake_handler.get_today_stats()

        # 正常なレコードのみ集計される
        self.assertAlmostEqual(game_minutes.get('Game1', 0), 30.0, places=1)
        self.assertNotIn('InvalidGame', game_minutes)
        self.assertNotIn('Game2', game_minutes)
        self.assertAlmostEqual(game_minutes.get('Game3', 0), 20.0, places=1)
        # 30分 + 20分 = 50分 = 3000秒
        self.assertAlmostEqual(total_seconds, 3000.0, places=1)

    def test_get_today_stats_empty_records(self):
        """レコードが空の場合."""
        fake_handler = FakeLogHandler()
        fake_handler.records = []

        game_minutes, total_seconds = fake_handler.get_today_stats()

        self.assertEqual(game_minutes, {})
        self.assertEqual(total_seconds, 0.0)


class TestGspreadServiceSheetProperty(unittest.TestCase):
    """GspreadService.sheetプロパティのテスト."""

    @patch('src.infra.gspread_service.gspread.service_account')
    def test_sheet_property_returns_worksheet(self, mock_sa):
        """sheetプロパティがワークシートを返す."""
        from src.infra.gspread_service import GspreadService

        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_gc.open_by_key.return_value.sheet1 = mock_sheet
        mock_sa.return_value = mock_gc

        service = GspreadService(cert_file_path='test.json', sheet_key='test_key')
        result = service.sheet

        self.assertEqual(result, mock_sheet)

    def test_sheet_property_raises_when_not_connected(self):
        """sheetプロパティが未接続時にRuntimeErrorを発生."""
        from src.infra.gspread_service import GspreadService

        service = GspreadService.__new__(GspreadService)
        service._sheet = None

        with self.assertRaises(RuntimeError) as ctx:
            _ = service.sheet

        self.assertIn('not connected', str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
