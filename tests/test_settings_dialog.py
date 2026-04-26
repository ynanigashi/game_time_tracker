import unittest
from unittest.mock import patch

from tests.test_stubs import install_stubs
install_stubs()

from src.infra.settings_config import EditableAppConfig
from src.ui.settings_dialog import SettingsDialog


class TestSettingsDialog(unittest.TestCase):
    def test_collect_returns_edited_values(self):
        loaded_config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome"],
            excluded_titles=["Settings"],
        )
        with patch(
            "src.ui.settings_dialog.load_editable_config",
            return_value=loaded_config,
        ):
            dialog = SettingsDialog()

        dialog.json_file_path_edit.setText("custom.json")
        dialog.browsers_edit.setPlainText("Chrome, Edge\nFirefox")
        collected = dialog._collect()

        self.assertEqual(collected.json_file_path, "custom.json")
        self.assertEqual(collected.browsers, ["Chrome", "Edge", "Firefox"])

    def test_save_calls_callback_on_success(self):
        loaded_config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome"],
            excluded_titles=["Settings"],
        )
        callback_called = []
        with patch(
            "src.ui.settings_dialog.load_editable_config",
            return_value=loaded_config,
        ), patch("src.ui.settings_dialog.save_editable_config") as mock_save:
            dialog = SettingsDialog(on_saved=lambda: callback_called.append(True))
            dialog._save()

        mock_save.assert_called_once()
        self.assertEqual(callback_called, [True])
        self.assertTrue(dialog.accepted)

    def test_select_json_file_updates_path(self):
        loaded_config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome"],
            excluded_titles=["Settings"],
        )
        with patch(
            "src.ui.settings_dialog.load_editable_config",
            return_value=loaded_config,
        ), patch(
            "src.ui.settings_dialog.QFileDialog.getOpenFileName",
            return_value=("C:/keys/service-account.json", "JSON Files (*.json)"),
        ):
            dialog = SettingsDialog()
            dialog._select_json_file()

        self.assertEqual(
            dialog.json_file_path_edit.text(),
            "C:/keys/service-account.json",
        )

    def test_select_json_file_keeps_path_when_cancelled(self):
        loaded_config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome"],
            excluded_titles=["Settings"],
        )
        with patch(
            "src.ui.settings_dialog.load_editable_config",
            return_value=loaded_config,
        ), patch(
            "src.ui.settings_dialog.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ):
            dialog = SettingsDialog()
            dialog._select_json_file()

        self.assertEqual(dialog.json_file_path_edit.text(), "service_account.json")

    def test_import_config_updates_fields_and_callback(self):
        loaded_config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome"],
            excluded_titles=["Settings"],
        )
        imported_config = EditableAppConfig(
            json_file_path="imported.json",
            log_sheet_key="imported_log",
            game_info_sheet_key="imported_game",
            game_info_sheet_gid=456,
            browsers=["Edge"],
            excluded_titles=["Store"],
        )
        callback_called = []
        with patch(
            "src.ui.settings_dialog.load_editable_config",
            return_value=loaded_config,
        ), patch(
            "src.ui.settings_dialog.QFileDialog.getOpenFileName",
            return_value=("C:/config/config.ini", "INI Files (*.ini)"),
        ), patch(
            "src.ui.settings_dialog.import_editable_config",
            return_value=imported_config,
        ) as mock_import:
            dialog = SettingsDialog(on_saved=lambda: callback_called.append(True))
            dialog._import_config()

        mock_import.assert_called_once_with("C:/config/config.ini")
        self.assertEqual(dialog.log_sheet_key_edit.text(), "imported_log")
        self.assertEqual(callback_called, [True])

    def test_export_config_writes_selected_ini(self):
        loaded_config = EditableAppConfig(
            json_file_path="service_account.json",
            log_sheet_key="log_key",
            game_info_sheet_key="game_key",
            game_info_sheet_gid=123,
            browsers=["Chrome"],
            excluded_titles=["Settings"],
        )
        with patch(
            "src.ui.settings_dialog.load_editable_config",
            return_value=loaded_config,
        ), patch(
            "src.ui.settings_dialog.QFileDialog.getSaveFileName",
            return_value=("C:/config/config.ini", "INI Files (*.ini)"),
        ), patch("src.ui.settings_dialog.export_editable_config") as mock_export:
            dialog = SettingsDialog()
            dialog._export_config()

        mock_export.assert_called_once()
        self.assertEqual(
            mock_export.call_args.kwargs["config_file_path"],
            "C:/config/config.ini",
        )


if __name__ == "__main__":
    unittest.main()
