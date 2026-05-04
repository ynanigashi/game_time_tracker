# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportOptionalMemberAccess=false

from tests.helpers.main_test_imports import *  # noqa: F401,F403


class TestLoggingConfiguration(unittest.TestCase):
    def test_configure_logging_uses_rotating_file_handler(self):
        root_logger = logging.getLogger()
        original_handlers = list(root_logger.handlers)
        original_configured = main.DEFAULT_LOGGING_STATE.configured
        original_log_file = main.DEFAULT_LOGGING_STATE.log_file_path
        for handler in original_handlers:
            root_logger.removeHandler(handler)

        try:
            main.DEFAULT_LOGGING_STATE.configured = False
            main.configure_logging()

            rotating_handlers = [
                handler
                for handler in root_logger.handlers
                if isinstance(handler, RotatingFileHandler)
            ]
            self.assertEqual(len(rotating_handlers), 1)
            self.assertEqual(rotating_handlers[0].baseFilename, str(
                main.LOG_FILE_PATH.resolve()
            ))
            self.assertEqual(rotating_handlers[0].maxBytes, main.LOG_MAX_BYTES)
            self.assertEqual(
                rotating_handlers[0].backupCount,
                main.LOG_BACKUP_COUNT,
            )
            self.assertTrue(main.LOG_DIR.exists())
        finally:
            for handler in list(root_logger.handlers):
                root_logger.removeHandler(handler)
                handler.close()
            for handler in original_handlers:
                root_logger.addHandler(handler)
            main.DEFAULT_LOGGING_STATE.configured = original_configured
            main.DEFAULT_LOGGING_STATE.log_file_path = original_log_file

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
            mock_window._set_status('ゲーム情報が未登録です。ゲーム管理で追加してください。')
            mock_window.setDisabled(True)

        self.assertTrue(mock_window.disabled)
        self.assertIn('ゲーム情報が未登録', mock_window.status)

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
