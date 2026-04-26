# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""config_loader.py のユニットテスト."""

from src.core import services
from src.infra.config_loader import ConfigLoader
from src.infra.settings_store import SettingsStore
from src.app import main
import configparser
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# 共通スタブをインストール
from tests.test_stubs import install_stubs
install_stubs()


class TestConfigLoaderValidation(unittest.TestCase):
    """ConfigLoaderの検証テスト."""

    def setUp(self):
        """テスト用の一時ディレクトリを作成."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """テスト用ファイルを削除."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_section_raises_key_error(self):
        """必須セクションがない場合はKeyErrorを送出."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[OTHER]\nkey=value\n")

        # config_loaderをインポート（mainからではなく直接）
        from src.infra import config_loader
        with self.assertRaises(KeyError) as ctx:
            config_loader.ConfigLoader(config_path)

        self.assertIn('LOGHANDLER', str(ctx.exception))

    def test_missing_key_raises_key_error(self):
        """必須キーがない場合はKeyErrorを送出."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\n")
            f.write("[GAMEINFO]\nsheet_key=abc\nsheet_gid=123\n")

        from src.infra import config_loader
        with self.assertRaises(KeyError) as ctx:
            config_loader.ConfigLoader(config_path)

        self.assertIn('sheet_key', str(ctx.exception))

    def test_invalid_sheet_gid_raises_value_error(self):
        """sheet_gidが整数でない場合はValueErrorを送出."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=abc\n")
            f.write("[GAMEINFO]\nsheet_key=abc\nsheet_gid=not_an_int\n")

        from src.infra import config_loader
        with self.assertRaises(ValueError) as ctx:
            config_loader.ConfigLoader(config_path).load()

        self.assertIn('sheet_gid', str(ctx.exception))

    def test_valid_config_loads_successfully(self):
        """有効な設定ファイルは正常に読み込める."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")

        from src.infra import config_loader
        cfg = config_loader.ConfigLoader(config_path).load()

        self.assertEqual(cfg.log_handler.cert_file_path, 'test.json')
        self.assertEqual(cfg.log_handler.sheet_key, 'log_key')
        self.assertEqual(cfg.game_info.sheet_key, 'game_key')
        self.assertEqual(cfg.game_info.sheet_gid, 12345)


class TestConfigLoaderGetList(unittest.TestCase):
    """ConfigLoader._get_list()のテスト."""

    def setUp(self):
        """テスト用の一時ディレクトリを作成."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """テスト用ファイルを削除."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_returns_default_when_section_missing(self):
        """セクションがない場合はデフォルトを返す."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")

        from src.infra import config_loader
        cfg = config_loader.ConfigLoader(config_path).load()

        # WINDOW_SCANセクションがないのでデフォルト
        self.assertEqual(cfg.window_scan.browsers, config_loader.DEFAULT_BROWSERS)

    def test_returns_default_when_key_missing(self):
        """キーがない場合はデフォルトを返す."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")
            f.write("[WINDOW_SCAN]\n")  # セクションはあるがキーがない

        from src.infra import config_loader
        cfg = config_loader.ConfigLoader(config_path).load()

        self.assertEqual(cfg.window_scan.browsers, config_loader.DEFAULT_BROWSERS)

    def test_returns_default_when_value_empty(self):
        """値が空の場合はデフォルトを返す."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")
            f.write("[WINDOW_SCAN]\nbrowsers=\n")  # 空の値

        from src.infra import config_loader
        cfg = config_loader.ConfigLoader(config_path).load()

        self.assertEqual(cfg.window_scan.browsers, config_loader.DEFAULT_BROWSERS)

    def test_returns_default_when_value_only_whitespace(self):
        """値が空白のみの場合はデフォルトを返す."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")
            f.write("[WINDOW_SCAN]\nbrowsers=  ,  ,  \n")  # 空白とカンマのみ

        from src.infra import config_loader
        cfg = config_loader.ConfigLoader(config_path).load()

        self.assertEqual(cfg.window_scan.browsers, config_loader.DEFAULT_BROWSERS)

    def test_parses_comma_separated_values(self):
        """カンマ区切りの値を正しくパースする."""
        config_path = os.path.join(self.temp_dir, 'test_config.ini')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("[LOGHANDLER]\njson_file_path=test.json\nsheet_key=log_key\n")
            f.write("[GAMEINFO]\nsheet_key=game_key\nsheet_gid=12345\n")
            f.write("[WINDOW_SCAN]\nbrowsers=Chrome, Firefox, Edge\n")

        from src.infra import config_loader
        cfg = config_loader.ConfigLoader(config_path).load()

        self.assertEqual(cfg.window_scan.browsers, ['Chrome', 'Firefox', 'Edge'])


class TestConfigLoaderSettingsStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_config(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join([
                "[LOGHANDLER]",
                "json_file_path=service_account.json",
                "sheet_key=log_key",
                "[GAMEINFO]",
                "sheet_key=game_key",
                "sheet_gid=12345",
            ]),
            encoding="utf-8",
        )

    def test_default_loader_imports_config_file_to_sqlite(self):
        config_path = self.base_dir / "config" / "config.ini"
        self._write_config(config_path)
        store = SettingsStore(self.base_dir / "data" / "settings.sqlite3")

        with patch("src.infra.runtime_paths.app_base_dir", return_value=self.base_dir):
            cfg = ConfigLoader(settings_store=store).load()

        self.assertEqual(cfg.log_handler.sheet_key, "log_key")
        loaded_from_db = store.load_config()
        self.assertEqual(loaded_from_db["GAMEINFO"]["sheet_gid"], "12345")

    def test_default_loader_reads_sqlite_when_config_file_missing(self):
        store = SettingsStore(self.base_dir / "data" / "settings.sqlite3")
        config = configparser.ConfigParser()
        config["LOGHANDLER"] = {
            "json_file_path": "service_account.json",
            "sheet_key": "log_key",
        }
        config["GAMEINFO"] = {
            "sheet_key": "game_key",
            "sheet_gid": "12345",
        }
        store.save_config(config)

        with patch("src.infra.runtime_paths.app_base_dir", return_value=self.base_dir):
            cfg = ConfigLoader(settings_store=store).load()

        self.assertEqual(cfg.game_info.sheet_key, "game_key")


class TestConfigLoaderExcludedTitles(unittest.TestCase):
    """ConfigLoaderのexcluded_titlesがwindow_scanに反映されるテスト."""

    def test_excluded_titles_default(self):
        """excluded_titlesのデフォルト値."""
        config_content = """
[LOGHANDLER]
json_file_path = service_account.json
sheet_key = test_key

[GAMEINFO]
sheet_key = test_key
sheet_gid = 123

[WINDOW_SCAN]
browsers = Chrome
"""
        with patch.object(main.ConfigLoader, '__init__', lambda self: None):
            loader = main.ConfigLoader()
            loader.config = configparser.ConfigParser()
            loader.config.read_string(config_content)
            cfg = loader.load()

        # デフォルト値が設定される
        self.assertEqual(cfg.window_scan.excluded_titles,
                         list(main.DEFAULT_EXCLUDED_TITLES))

    def test_excluded_titles_custom_comma_separated(self):
        """excluded_titlesのカンマ区切り値."""
        config_content = """
[LOGHANDLER]
json_file_path = service_account.json
sheet_key = test_key

[GAMEINFO]
sheet_key = test_key
sheet_gid = 123

[WINDOW_SCAN]
browsers = Chrome
exclude_titles = Settings, Task Manager, Control Panel
"""
        with patch.object(main.ConfigLoader, '__init__', lambda self: None):
            loader = main.ConfigLoader()
            loader.config = configparser.ConfigParser()
            loader.config.read_string(config_content)
            cfg = loader.load()

        # カスタム値が設定される
        self.assertEqual(cfg.window_scan.excluded_titles, [
                         'Settings', 'Task Manager', 'Control Panel'])

    def test_excluded_titles_empty_uses_default(self):
        """excluded_titlesが空ならデフォルト."""
        config_content = """
[LOGHANDLER]
json_file_path = service_account.json
sheet_key = test_key

[GAMEINFO]
sheet_key = test_key
sheet_gid = 123

[WINDOW_SCAN]
browsers = Chrome
exclude_titles =
"""
        with patch.object(main.ConfigLoader, '__init__', lambda self: None):
            loader = main.ConfigLoader()
            loader.config = configparser.ConfigParser()
            loader.config.read_string(config_content)
            cfg = loader.load()

        # デフォルト値が設定される
        self.assertEqual(cfg.window_scan.excluded_titles,
                         list(main.DEFAULT_EXCLUDED_TITLES))

    def test_excluded_titles_reflected_in_window_scanner(self):
        """excluded_titlesがWindowScannerに反映される."""
        excluded = ['CustomExclude1', 'CustomExclude2']

        scanner = services.WindowScanner(excluded_titles=excluded)

        self.assertEqual(scanner.excluded_titles, set(excluded))

    def test_window_scanner_excludes_matching_titles(self):
        """WindowScannerが除外タイトルにマッチするウィンドウを除外."""
        excluded = ['Settings', 'Task Manager']

        scanner = services.WindowScanner(excluded_titles=excluded)

        # 除外タイトルがセットに含まれる
        self.assertIn('Settings', scanner.excluded_titles)
        self.assertIn('Task Manager', scanner.excluded_titles)


if __name__ == "__main__":
    unittest.main()
