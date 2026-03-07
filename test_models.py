# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportOptionalMemberAccess=false
"""models.py のユニットテスト."""

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

# 共通スタブをインストール（他モジュール import 前に実行）
from test_stubs import install_stubs
install_stubs()

import models
from text_utils import normalize_title


class TestGameEntry(unittest.TestCase):
    def test_matches_window_browser_game_allows_browser_titles(self):
        game = models.GameEntry(game_title="BrowserGame", window_title="BrowserGame", is_browser_game=True)
        self.assertTrue(
            game.matches_window(
                normalize_title("BrowserGame - Chrome"),
                browsers=[normalize_title("Chrome")],
            )
        )

    def test_matches_window_uses_normalized_inputs(self):
        game = models.GameEntry(
            game_title="PlayGo",
            window_title="PlayGo.gg – Play Go Online",
            is_browser_game=True,
        )
        title = "PLAYGO.GG - PLAY GO ONLINE - GOOGLE CHROME"
        self.assertTrue(
            game.matches_window(
                normalize_title(title),
                browsers=[normalize_title("Google Chrome")],
            )
        )

    def test_matches_window_normal_game_excludes_browsers(self):
        game = models.GameEntry(game_title="NormalGame", window_title="NormalGame", is_browser_game=False)
        self.assertFalse(
            game.matches_window(
                normalize_title("NormalGame - Chrome"),
                browsers=[normalize_title("Chrome")],
            )
        )

    def test_window_title_change_invalidates_normalized_cache(self):
        game = models.GameEntry(
            game_title="WebGame",
            window_title="OldTitle",
            is_browser_game=True,
        )

        # Warm cache.
        self.assertTrue(
            game.matches_window(
                normalize_title("OldTitle - Chrome"),
                browsers=[normalize_title("Chrome")],
            )
        )
        self.assertIsNotNone(game._normalized_window_title)

        game.window_title = "NewTitle"

        self.assertTrue(
            game.matches_window(
                normalize_title("NewTitle - Chrome"),
                browsers=[normalize_title("Chrome")],
            )
        )
        self.assertFalse(
            game.matches_window(
                normalize_title("OldTitle - Chrome"),
                browsers=[normalize_title("Chrome")],
            )
        )


class TestNormalizeTitle(unittest.TestCase):
    def test_normalizes_case_dash_and_whitespace(self):
        value = "PlayGo.gg –  Play Go Online"
        self.assertEqual(normalize_title(value), "playgo.gg - play go online")


class TestGameEntryInactive(unittest.TestCase):
    """GameEntryの非アクティブ機能テスト."""

    def test_initial_state_not_inactive(self):
        """初期状態では非アクティブではない."""
        game = models.GameEntry(game_title="Test", window_title="Test")
        self.assertFalse(game.is_inactive())
        self.assertEqual(game.get_inactive_seconds(), 0.0)

    def test_set_inactive_marks_inactive(self):
        """set_inactive()で非アクティブ状態になる."""
        game = models.GameEntry(game_title="Test", window_title="Test")
        game.set_inactive()
        self.assertTrue(game.is_inactive())
        self.assertIsNotNone(game.inactive_since)

    def test_set_active_clears_inactive(self):
        """set_active()で非アクティブ状態がクリアされる."""
        game = models.GameEntry(game_title="Test", window_title="Test")
        game.set_inactive()
        game.set_active()
        self.assertFalse(game.is_inactive())
        self.assertIsNone(game.inactive_since)

    def test_start_session_clears_inactive(self):
        """start_session()で非アクティブ状態がクリアされる."""
        game = models.GameEntry(game_title="Test", window_title="Test")
        game.inactive_since = datetime.now()
        game.start_session()
        self.assertIsNone(game.inactive_since)

    def test_end_session_clears_inactive(self):
        """end_session()で非アクティブ状態がクリアされる."""
        game = models.GameEntry(game_title="Test", window_title="Test", is_playing=True)
        game.start_time = datetime.now()
        game.inactive_since = datetime.now()
        game.end_session()
        self.assertIsNone(game.inactive_since)

    def test_get_inactive_seconds_returns_elapsed_time(self):
        """get_inactive_seconds()は経過秒数を返す."""
        game = models.GameEntry(game_title="Test", window_title="Test")
        game.inactive_since = datetime.now() - timedelta(seconds=30)
        elapsed = game.get_inactive_seconds()
        self.assertGreaterEqual(elapsed, 29)
        self.assertLess(elapsed, 32)


class TestParseRecord(unittest.TestCase):
    """_parse_record()のテスト."""

    def test_parse_valid_record(self):
        """正常なレコードをパースできる."""
        record = {
            'start_time': '2026/01/18 10:00:00',
            'end_time': '2026/01/18 11:30:00',
            'title': 'TestGame',
        }
        result = models.parse_record(record)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.start, datetime(2026, 1, 18, 10, 0, 0))
        self.assertEqual(result.end, datetime(2026, 1, 18, 11, 30, 0))
        self.assertEqual(result.game_title, 'TestGame')

    def test_parse_record_missing_title_uses_default(self):
        """titleがない場合は'不明'を使用."""
        record = {
            'start_time': '2026/01/18 10:00:00',
            'end_time': '2026/01/18 11:00:00',
        }
        result = models.parse_record(record)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.game_title, '不明')

    def test_parse_record_invalid_date_format(self):
        """不正な日付フォーマットはNoneを返す."""
        record = {
            'start_time': '2026-01-18 10:00:00',  # 間違ったフォーマット
            'end_time': '2026/01/18 11:00:00',
            'title': 'TestGame',
        }
        result = models.parse_record(record)
        self.assertIsNone(result)

    def test_parse_record_missing_start_time(self):
        """start_timeがない場合はNoneを返す."""
        record = {
            'end_time': '2026/01/18 11:00:00',
            'title': 'TestGame',
        }
        result = models.parse_record(record)
        self.assertIsNone(result)

    def test_parse_record_missing_end_time(self):
        """end_timeがない場合はNoneを返す."""
        record = {
            'start_time': '2026/01/18 10:00:00',
            'title': 'TestGame',
        }
        result = models.parse_record(record)
        self.assertIsNone(result)

    def test_parse_record_empty_dict(self):
        """空の辞書はNoneを返す."""
        result = models.parse_record({})
        self.assertIsNone(result)


class TestParsedRecordDataclass(unittest.TestCase):
    """ParsedRecordデータクラスのテスト."""

    def test_parsed_record_attributes(self):
        """ParsedRecordの属性が正しく設定される."""
        parsed = models.ParsedRecord(
            start=datetime(2026, 1, 18, 10, 0, 0),
            end=datetime(2026, 1, 18, 11, 0, 0),
            game_title='TestGame',
        )
        self.assertEqual(parsed.start, datetime(2026, 1, 18, 10, 0, 0))
        self.assertEqual(parsed.end, datetime(2026, 1, 18, 11, 0, 0))
        self.assertEqual(parsed.game_title, 'TestGame')

    def test_parsed_record_duration_calculation(self):
        """ParsedRecordからプレイ時間を計算できる."""
        parsed = models.ParsedRecord(
            start=datetime(2026, 1, 18, 10, 0, 0),
            end=datetime(2026, 1, 18, 11, 30, 0),
            game_title='TestGame',
        )
        duration_minutes = (parsed.end - parsed.start).total_seconds() / 60
        self.assertEqual(duration_minutes, 90)


class TestGameEntryStartSession(unittest.TestCase):
    """GameEntry.start_session()のテスト."""

    def test_start_session_sets_is_playing_true(self):
        """start_session()でis_playing=Trueになる."""
        game = models.GameEntry(game_title="Test", window_title="Test")
        self.assertFalse(game.is_playing)
        game.start_session()
        self.assertTrue(game.is_playing)

    def test_start_session_sets_start_time(self):
        """start_session()でstart_timeが設定される."""
        game = models.GameEntry(game_title="Test", window_title="Test")
        self.assertIsNone(game.start_time)
        before = datetime.now()
        game.start_session()
        after = datetime.now()
        self.assertIsNotNone(game.start_time)
        self.assertGreaterEqual(game.start_time, before)
        self.assertLessEqual(game.start_time, after)


class TestGameEntryEndSession(unittest.TestCase):
    """GameEntry.end_session()のテスト."""

    def test_end_session_returns_times(self):
        """end_session()は開始・終了時刻を返す."""
        game = models.GameEntry(game_title="Test", window_title="Test")
        game.start_session()
        original_start = game.start_time
        start_time, end_time = game.end_session()
        self.assertEqual(start_time, original_start)
        self.assertIsNotNone(end_time)
        self.assertGreaterEqual(end_time, start_time)

    def test_end_session_clears_state(self):
        """end_session()後はis_playing=False、start_time=None."""
        game = models.GameEntry(game_title="Test", window_title="Test")
        game.start_session()
        game.end_session()
        self.assertFalse(game.is_playing)
        self.assertIsNone(game.start_time)

    def test_end_session_without_start_returns_none(self):
        """開始していない状態でend_session()するとNoneを返す."""
        game = models.GameEntry(game_title="Test", window_title="Test")
        start_time, end_time = game.end_session()
        self.assertIsNone(start_time)
        self.assertIsNone(end_time)


class TestGameEntryMatchesWindow(unittest.TestCase):
    """GameEntry.matches_window()のテスト（部分一致含む）."""

    def test_partial_match_in_title(self):
        """window_titleがウィンドウタイトルの一部として含まれる場合にマッチ."""
        game = models.GameEntry(game_title="Terraria", window_title="Terraria")
        self.assertTrue(
            game.matches_window(normalize_title("Terraria: Official Server"), browsers=[])
        )

    def test_no_match_if_not_contained(self):
        """window_titleが含まれない場合はマッチしない."""
        game = models.GameEntry(game_title="Terraria", window_title="Terraria")
        self.assertFalse(
            game.matches_window(normalize_title("Terra - Some Other App"), browsers=[])
        )

    def test_browser_game_matches_browser_title(self):
        """ブラウザゲームはブラウザタイトルでもマッチ."""
        game = models.GameEntry(
            game_title="WebGame",
            window_title="WebGame",
            is_browser_game=True,
        )
        self.assertTrue(
            game.matches_window(
                normalize_title("WebGame - Google Chrome"),
                browsers=[normalize_title("Google Chrome")],
            )
        )

    def test_non_browser_game_rejects_browser_title(self):
        """通常ゲームはブラウザタイトルを拒否."""
        game = models.GameEntry(
            game_title="SteamGame",
            window_title="SteamGame",
            is_browser_game=False,
        )
        self.assertFalse(
            game.matches_window(
                normalize_title("SteamGame - Google Chrome"),
                browsers=[normalize_title("Google Chrome")],
            )
        )

    def test_non_browser_game_matches_non_browser_title(self):
        """通常ゲームは非ブラウザタイトルでマッチ."""
        game = models.GameEntry(
            game_title="SteamGame",
            window_title="SteamGame",
            is_browser_game=False,
        )
        self.assertTrue(
            game.matches_window(
                normalize_title("SteamGame v1.2.3"),
                browsers=[normalize_title("Google Chrome")],
            )
        )


class TestParseBool(unittest.TestCase):
    """_parse_bool()のテスト."""

    def test_true_string(self):
        """'TRUE'文字列はTrueを返す."""
        self.assertTrue(models.parse_bool("TRUE"))

    def test_true_lowercase(self):
        """'true'文字列はTrueを返す."""
        self.assertTrue(models.parse_bool("true"))

    def test_true_mixed_case(self):
        """'True'文字列はTrueを返す."""
        self.assertTrue(models.parse_bool("True"))

    def test_false_string(self):
        """'FALSE'文字列はFalseを返す."""
        self.assertFalse(models.parse_bool("FALSE"))

    def test_empty_string(self):
        """空文字列はFalseを返す."""
        self.assertFalse(models.parse_bool(""))

    def test_other_string(self):
        """その他の文字列はFalseを返す."""
        self.assertFalse(models.parse_bool("yes"))
        self.assertFalse(models.parse_bool("1"))


if __name__ == "__main__":
    unittest.main()
