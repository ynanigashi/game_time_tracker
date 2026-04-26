import configparser
import tempfile
import unittest
from pathlib import Path

from src.infra.settings_config import (
    EditableAppConfig,
    export_editable_config,
    import_editable_config,
    list_to_text,
    load_editable_config,
    parse_list_text,
    save_editable_config,
)
from src.infra.settings_store import SettingsStore
from src.infra.config_loader import (
    PLAY_LOG_BACKUP_MODE_LOCAL_ONLY,
    PLAY_LOG_BACKUP_MODE_SPREADSHEET,
)


class TestSettingsConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.config_path = self.base_dir / "config" / "config.ini"
        self.store = SettingsStore(self.base_dir / "data" / "settings.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_list_text_accepts_lines_and_commas(self):
        self.assertEqual(
            parse_list_text("Chrome, Edge\nFirefox", ["Default"]),
            ["Chrome", "Edge", "Firefox"],
        )

    def test_parse_list_text_uses_default_when_empty(self):
        self.assertEqual(parse_list_text("  \n , ", ["Default"]), ["Default"])

    def test_list_to_text_uses_one_item_per_line(self):
        self.assertEqual(list_to_text(["Chrome", "Edge"]), "Chrome\nEdge")

    def test_save_editable_config_writes_sqlite_only(self):
        config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome", "Edge"],
            excluded_titles=["Settings"],
        )

        save_editable_config(
            config,
            settings_store=self.store,
        )

        self.assertFalse(self.config_path.exists())

        loaded = self.store.load_config()
        self.assertEqual(loaded["GAMEINFO"]["sheet_gid"], "123")
        self.assertEqual(
            loaded["LOGHANDLER"]["backup_mode"],
            PLAY_LOG_BACKUP_MODE_SPREADSHEET,
        )
        self.assertEqual(loaded["LOGHANDLER"]["sheet_gid"], "")
        self.assertEqual(loaded["LOGHANDLER"]["sync_conflict_policy"], "overwrite")

    def test_load_editable_config_reads_saved_values(self):
        config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome"],
            excluded_titles=["Settings"],
        )
        save_editable_config(
            config,
            settings_store=self.store,
        )

        loaded = load_editable_config(
            settings_store=self.store,
        )

        self.assertEqual(loaded.log_sheet_key, "log_key")
        self.assertEqual(loaded.browsers, ["Chrome"])

    def test_save_editable_config_rejects_missing_required_value(self):
        config = EditableAppConfig(
            json_file_path="",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=[],
            excluded_titles=[],
        )

        with self.assertRaises(ValueError):
            save_editable_config(
                config,
                settings_store=self.store,
            )

    def test_local_only_mode_allows_empty_log_sheet_key(self):
        config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome"],
            excluded_titles=["Settings"],
            play_log_backup_mode=PLAY_LOG_BACKUP_MODE_LOCAL_ONLY,
        )

        save_editable_config(config, settings_store=self.store)

        loaded = load_editable_config(settings_store=self.store)
        self.assertEqual(loaded.play_log_backup_mode, PLAY_LOG_BACKUP_MODE_LOCAL_ONLY)
        self.assertEqual(loaded.log_sheet_key, "")

    def test_export_editable_config_writes_ini(self):
        config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome", "Edge"],
            excluded_titles=["Settings"],
        )

        export_editable_config(config, config_file_path=str(self.config_path))

        parser = configparser.ConfigParser()
        parser.read(self.config_path, encoding="utf-8")
        self.assertEqual(parser["LOGHANDLER"]["sheet_key"], "log_key")
        self.assertEqual(
            parser["LOGHANDLER"]["backup_mode"],
            PLAY_LOG_BACKUP_MODE_SPREADSHEET,
        )
        self.assertEqual(parser["WINDOW_SCAN"]["browsers"], "Chrome, Edge")

    def test_log_sheet_gid_roundtrip(self):
        config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome"],
            excluded_titles=["Settings"],
            log_sheet_gid=456,
        )

        save_editable_config(config, settings_store=self.store)
        loaded = load_editable_config(settings_store=self.store)

        self.assertEqual(loaded.log_sheet_gid, 456)

    def test_sync_conflict_policy_roundtrip(self):
        config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome"],
            excluded_titles=["Settings"],
            sync_conflict_policy="new_id",
        )

        save_editable_config(config, settings_store=self.store)
        loaded = load_editable_config(settings_store=self.store)

        self.assertEqual(loaded.sync_conflict_policy, "new_id")

    def test_import_editable_config_writes_sqlite(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            "\n".join(
                [
                    "[LOGHANDLER]",
                    "json_file_path=service_account.json",
                    "sheet_key=log_key",
                    "[GAMEINFO]",
                    "sheet_key=game_key",
                    "sheet_gid=123",
                ]
            ),
            encoding="utf-8",
        )

        imported = import_editable_config(
            str(self.config_path),
            settings_store=self.store,
        )

        self.assertEqual(imported.log_sheet_key, "log_key")
        loaded = self.store.load_config()
        self.assertEqual(loaded["GAMEINFO"]["sheet_gid"], "123")


if __name__ == "__main__":
    unittest.main()
