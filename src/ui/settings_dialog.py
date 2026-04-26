"""Settings editor dialog."""

import logging
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.infra.config_loader import (
    DEFAULT_BROWSERS,
    DEFAULT_EXCLUDED_TITLES,
    PLAY_LOG_BACKUP_MODE_LOCAL_ONLY,
    PLAY_LOG_BACKUP_MODE_SPREADSHEET,
    PLAY_LOG_SYNC_CONFLICT_NEW_ID,
    PLAY_LOG_SYNC_CONFLICT_OVERWRITE,
)
from src.infra.runtime_paths import resolve_config_file
from src.infra.settings_config import (
    EditableAppConfig,
    export_editable_config,
    import_editable_config,
    list_to_text,
    load_editable_config,
    parse_list_text,
    save_editable_config,
)

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Dialog for editing runtime settings."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._on_saved = on_saved
        self.setWindowTitle("設定")
        self.resize(620, 560)

        self.json_file_path_edit = QLineEdit(self)
        self.json_file_browse_button = QPushButton("参照...", self)
        self.json_file_browse_button.clicked.connect(self._select_json_file)
        self.log_sheet_key_edit = QLineEdit(self)
        self.log_sheet_gid_edit = QLineEdit(self)
        self.play_log_backup_mode_combo = QComboBox(self)
        self.play_log_backup_mode_combo.addItem(
            "ローカルのみで運用",
            PLAY_LOG_BACKUP_MODE_LOCAL_ONLY,
        )
        self.play_log_backup_mode_combo.addItem(
            "スプレッドシートにバックアップ",
            PLAY_LOG_BACKUP_MODE_SPREADSHEET,
        )
        self.play_log_backup_mode_combo.currentIndexChanged.connect(
            self._sync_backup_mode_fields
        )
        self.sync_conflict_policy_combo = QComboBox(self)
        self.sync_conflict_policy_combo.addItem(
            "スプシを上書き",
            PLAY_LOG_SYNC_CONFLICT_OVERWRITE,
        )
        self.sync_conflict_policy_combo.addItem(
            "別IDで追加",
            PLAY_LOG_SYNC_CONFLICT_NEW_ID,
        )
        self.game_info_sheet_key_edit = QLineEdit(self)
        self.game_info_sheet_gid_edit = QLineEdit(self)
        self.browsers_edit = QTextEdit(self)
        self.excluded_titles_edit = QTextEdit(self)
        self.status_label = QLabel("", self)
        self.import_button = QPushButton("設定Import", self)
        self.export_button = QPushButton("設定Export", self)
        self.import_button.clicked.connect(self._import_config)
        self.export_button.clicked.connect(self._export_config)

        self._build_layout()
        self._load()

    def _build_layout(self) -> None:
        form = QFormLayout()

        json_file_row = QWidget(self)
        json_file_layout = QHBoxLayout(json_file_row)
        json_file_layout.setContentsMargins(0, 0, 0, 0)
        json_file_layout.addWidget(self.json_file_path_edit)
        json_file_layout.addWidget(self.json_file_browse_button)

        form.addRow("認証JSON", json_file_row)
        form.addRow("プレイログ保存", self.play_log_backup_mode_combo)
        form.addRow("ログシート key", self.log_sheet_key_edit)
        form.addRow("ログシート sheet_gid", self.log_sheet_gid_edit)
        form.addRow("ID重複時", self.sync_conflict_policy_combo)
        form.addRow("ゲーム情報シート key", self.game_info_sheet_key_edit)
        form.addRow("ゲーム情報 sheet_gid", self.game_info_sheet_gid_edit)
        form.addRow("対象ブラウザ", self.browsers_edit)
        form.addRow("除外タイトル", self.excluded_titles_edit)

        file_buttons = QHBoxLayout()
        file_buttons.addWidget(self.import_button)
        file_buttons.addWidget(self.export_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(file_buttons)
        layout.addWidget(self.status_label)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _apply_config(self, config: EditableAppConfig) -> None:
        self.json_file_path_edit.setText(config.json_file_path)
        backup_mode_index = self.play_log_backup_mode_combo.findData(
            config.play_log_backup_mode
        )
        self.play_log_backup_mode_combo.setCurrentIndex(
            backup_mode_index if backup_mode_index >= 0 else 1
        )
        self.log_sheet_key_edit.setText(config.log_sheet_key)
        self.log_sheet_gid_edit.setText(
            "" if config.log_sheet_gid is None else str(config.log_sheet_gid)
        )
        conflict_policy_index = self.sync_conflict_policy_combo.findData(
            config.sync_conflict_policy
        )
        self.sync_conflict_policy_combo.setCurrentIndex(
            conflict_policy_index if conflict_policy_index >= 0 else 0
        )
        self._sync_backup_mode_fields()
        self.game_info_sheet_key_edit.setText(config.game_info_sheet_key)
        self.game_info_sheet_gid_edit.setText(str(config.game_info_sheet_gid))
        self.browsers_edit.setPlainText(list_to_text(config.browsers))
        self.excluded_titles_edit.setPlainText(list_to_text(config.excluded_titles))

    def _select_json_file(self) -> None:
        current_path = self.json_file_path_edit.text().strip()
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "認証JSONを選択",
            current_path,
            "JSON Files (*.json);;All Files (*)",
        )
        if selected_path:
            self.json_file_path_edit.setText(selected_path)

    def _select_config_file_for_import(self) -> str:
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "設定INIをImport",
            str(resolve_config_file()),
            "INI Files (*.ini);;All Files (*)",
        )
        return selected_path

    def _select_config_file_for_export(self) -> str:
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "設定INIをExport",
            str(resolve_config_file()),
            "INI Files (*.ini);;All Files (*)",
        )
        return selected_path

    def _load(self) -> None:
        try:
            config = load_editable_config()
        except Exception as exc:
            logger.info("Settings are not configured yet: %s", exc)
            self.status_label.setText("設定が未作成です。入力して保存してください。")
            config = EditableAppConfig(
                json_file_path="service_account.json",
                log_sheet_key="",
                game_info_sheet_key="",
                game_info_sheet_gid=0,
                browsers=list(DEFAULT_BROWSERS),
                excluded_titles=list(DEFAULT_EXCLUDED_TITLES),
                play_log_backup_mode=PLAY_LOG_BACKUP_MODE_SPREADSHEET,
                log_sheet_gid=None,
                sync_conflict_policy=PLAY_LOG_SYNC_CONFLICT_OVERWRITE,
            )

        self._apply_config(config)

    def _collect(self) -> EditableAppConfig:
        try:
            sheet_gid = int(self.game_info_sheet_gid_edit.text().strip())
        except ValueError as exc:
            raise ValueError("ゲーム情報 sheet_gid は整数で指定してください") from exc
        log_sheet_gid_text = self.log_sheet_gid_edit.text().strip()
        try:
            log_sheet_gid = int(log_sheet_gid_text) if log_sheet_gid_text else None
        except ValueError as exc:
            raise ValueError("ログシート sheet_gid は整数で指定してください") from exc

        return EditableAppConfig(
            json_file_path=self.json_file_path_edit.text().strip(),
            play_log_backup_mode=str(self.play_log_backup_mode_combo.currentData()),
            log_sheet_gid=log_sheet_gid,
            sync_conflict_policy=str(self.sync_conflict_policy_combo.currentData()),
            log_sheet_key=self.log_sheet_key_edit.text().strip(),
            game_info_sheet_key=self.game_info_sheet_key_edit.text().strip(),
            game_info_sheet_gid=sheet_gid,
            browsers=parse_list_text(
                self.browsers_edit.toPlainText(),
                list(DEFAULT_BROWSERS),
            ),
            excluded_titles=parse_list_text(
                self.excluded_titles_edit.toPlainText(),
                list(DEFAULT_EXCLUDED_TITLES),
            ),
        )

    def _sync_backup_mode_fields(self, *_args) -> None:
        backup_enabled = (
            self.play_log_backup_mode_combo.currentData()
            == PLAY_LOG_BACKUP_MODE_SPREADSHEET
        )
        self.log_sheet_key_edit.setEnabled(backup_enabled)
        self.log_sheet_gid_edit.setEnabled(backup_enabled)
        self.sync_conflict_policy_combo.setEnabled(backup_enabled)

    def _save(self) -> None:
        try:
            save_editable_config(self._collect())
        except Exception as exc:
            logger.exception("Failed to save settings")
            QMessageBox.warning(self, "設定エラー", str(exc))
            return

        if self._on_saved is not None:
            self._on_saved()
        self.accept()

    def _import_config(self) -> None:
        selected_path = self._select_config_file_for_import()
        if not selected_path:
            return

        try:
            config = import_editable_config(selected_path)
        except Exception as exc:
            logger.exception("Failed to import settings")
            QMessageBox.warning(self, "Importエラー", str(exc))
            return

        self._apply_config(config)
        self.status_label.setText("設定をImportしました。")
        if self._on_saved is not None:
            self._on_saved()

    def _export_config(self) -> None:
        selected_path = self._select_config_file_for_export()
        if not selected_path:
            return

        try:
            exported_path = export_editable_config(
                self._collect(),
                config_file_path=selected_path,
            )
        except Exception as exc:
            logger.exception("Failed to export settings")
            QMessageBox.warning(self, "Exportエラー", str(exc))
            return

        self.status_label.setText(f"設定をExportしました: {exported_path}")
