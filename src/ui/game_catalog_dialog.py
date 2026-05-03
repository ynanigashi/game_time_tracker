"""Game catalog editor dialog."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.models import GameEntry
from src.infra.config_loader import ConfigLoader
from src.infra.game_catalog_store import GameCatalogPushResult, GameCatalogStore
from src.infra.gspread_service import GspreadService

logger = logging.getLogger(__name__)


class GameCatalogDialog(QDialog):
    """Dialog for adding, editing, and deleting local game definitions."""

    COLUMNS = ("ID", "ゲーム", "ウィンドウタイトル", "フレンド", "ブラウザ")

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        game_store: Optional[GameCatalogStore] = None,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.game_store = game_store or GameCatalogStore()
        self._on_saved = on_saved
        self._close_sync_done = False
        self.setWindowTitle("ゲーム管理")
        self.resize(760, 520)

        self.table = QTableWidget(self)
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.table.setColumnHidden(0, True)
        self.table.itemSelectionChanged.connect(self._apply_selected_row)

        self.game_title_edit = QLineEdit(self)
        self.window_title_edit = QLineEdit(self)
        self.play_with_friends_check = QCheckBox(self)
        self.is_browser_game_check = QCheckBox(self)
        self.status_label = QLabel("", self)
        self.add_button = QPushButton("追加", self)
        self.update_button = QPushButton("更新", self)
        self.delete_button = QPushButton("削除", self)
        self.pull_button = QPushButton("スプシから取得", self)
        self.push_button = QPushButton("スプシへ送信", self)
        self.close_button = QPushButton("閉じる", self)

        self.add_button.clicked.connect(self._add_game)
        self.update_button.clicked.connect(self._update_game)
        self.delete_button.clicked.connect(self._delete_game)
        self.pull_button.clicked.connect(self._sync_from_spreadsheet)
        self.push_button.clicked.connect(self._push_to_spreadsheet)
        self.close_button.clicked.connect(self._close_dialog)

        self._build_layout()
        self._load_games()

    def _build_layout(self) -> None:
        form = QFormLayout()
        form.addRow("ゲーム名", self.game_title_edit)
        form.addRow("ウィンドウタイトル", self.window_title_edit)
        form.addRow("フレンドとプレイ", self.play_with_friends_check)
        form.addRow("ブラウザゲーム", self.is_browser_game_check)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.update_button)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.pull_button)
        buttons.addWidget(self.push_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)
        self.setLayout(layout)

    def _load_games(self) -> None:
        games = self.game_store.load_games()
        self.table.setRowCount(len(games))
        for row, game in enumerate(games):
            values = [
                game.game_id,
                game.game_title,
                game.window_title,
                "TRUE" if game.play_with_friends else "FALSE",
                "TRUE" if game.is_browser_game else "FALSE",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def _selected_row(self) -> int:
        row = self.table.currentRow()
        return row if row >= 0 else -1

    def _selected_game_id(self) -> str:
        row = self._selected_row()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        return item.text() if item is not None else ""

    def _apply_selected_row(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        self.game_title_edit.setText(self._table_text(row, 1))
        self.window_title_edit.setText(self._table_text(row, 2))
        self.play_with_friends_check.setChecked(self._table_text(row, 3) == "TRUE")
        self.is_browser_game_check.setChecked(self._table_text(row, 4) == "TRUE")

    def _table_text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text() if item is not None else ""

    def _collect_game(self, *, game_id: str = "") -> GameEntry:
        return GameEntry(
            game_id=game_id,
            game_title=self.game_title_edit.text().strip(),
            window_title=self.window_title_edit.text().strip(),
            play_with_friends=self.play_with_friends_check.isChecked(),
            is_browser_game=self.is_browser_game_check.isChecked(),
        )

    def _notify_saved(self) -> None:
        if self._on_saved is not None:
            self._on_saved()

    def _clear_form(self) -> None:
        self.game_title_edit.setText("")
        self.window_title_edit.setText("")
        self.play_with_friends_check.setChecked(False)
        self.is_browser_game_check.setChecked(False)

    def prepare_new_game(self, *, window_title: str = "") -> None:
        """Prepare the form for adding a new game."""
        self._clear_form()
        self.window_title_edit.setText(window_title.strip())

    def sync_on_open(self) -> None:
        """Best-effort game catalog sync when the dialog is opened."""
        try:
            service = self._game_info_service()
            push_result = self._push_local_games(service)
            if push_result.failed:
                self.status_label.setText(
                    "自動同期の取得をスキップしました: "
                    f"送信失敗 {push_result.failed} 件"
                )
                return
            records = service.get_all_records()
            pull_result = self.game_store.sync_records_from_spreadsheet(records)
        except Exception as exc:
            logger.info("Skipped game catalog open sync: %s", exc)
            self.status_label.setText(f"自動同期をスキップしました: {exc}")
            return

        self._clear_form()
        self._load_games()
        self._notify_saved()
        self.status_label.setText(
            "自動同期しました: "
            f"送信 {push_result.sent} 件 / 取得 {pull_result.received} 件"
        )

    def _sync_on_close(self) -> None:
        if self._close_sync_done:
            return
        self._close_sync_done = True
        try:
            service = self._game_info_service()
            result = self._push_local_games(service)
        except Exception as exc:
            logger.info("Skipped game catalog close sync: %s", exc)
            self.status_label.setText(f"終了時同期をスキップしました: {exc}")
            return

        self.status_label.setText(
            "終了時同期しました: "
            f"送信 {result.sent} 件 / 更新 {result.updated} 件 / "
            f"追加 {result.appended} 件 / 失敗 {result.failed} 件"
        )

    def _close_dialog(self) -> None:
        self._sync_on_close()
        self.accept()

    def closeEvent(self, event) -> None:
        self._sync_on_close()
        super().closeEvent(event)

    def _add_game(self) -> None:
        try:
            self.game_store.save_game(self._collect_game())
        except Exception as exc:
            logger.exception("Failed to add game")
            QMessageBox.warning(self, "ゲーム管理エラー", str(exc))
            return
        self._clear_form()
        self._load_games()
        self._notify_saved()

    def _update_game(self) -> None:
        game_id = self._selected_game_id()
        if not game_id:
            QMessageBox.warning(self, "ゲーム管理エラー", "更新するゲームを選択してください")
            return
        try:
            self.game_store.save_game(self._collect_game(game_id=game_id))
        except Exception as exc:
            logger.exception("Failed to update game")
            QMessageBox.warning(self, "ゲーム管理エラー", str(exc))
            return
        self._load_games()
        self._notify_saved()

    def _delete_game(self) -> None:
        game_id = self._selected_game_id()
        if not game_id:
            QMessageBox.warning(self, "ゲーム管理エラー", "削除するゲームを選択してください")
            return
        try:
            self.game_store.delete_game(game_id)
        except Exception as exc:
            logger.exception("Failed to delete game")
            QMessageBox.warning(self, "ゲーム管理エラー", str(exc))
            return
        self._clear_form()
        self._load_games()
        self._notify_saved()

    def _sync_from_spreadsheet(self) -> None:
        try:
            service = self._game_info_service()
            records = service.get_all_records()
            result = self.game_store.sync_records_from_spreadsheet(records)
        except Exception as exc:
            logger.exception("Failed to sync game catalog from spreadsheet")
            QMessageBox.warning(self, "ゲーム管理エラー", str(exc))
            return

        self._clear_form()
        self._load_games()
        self._notify_saved()
        self.status_label.setText(
            "スプシから取得しました: "
            f"取得 {result.received} 件 / 反映 {result.imported} 件 / "
            f"無効化 {result.disabled} 件"
        )

    def _push_to_spreadsheet(self) -> None:
        try:
            service = self._game_info_service()
            result = self._push_local_games(service)
        except Exception as exc:
            logger.exception("Failed to push game catalog to spreadsheet")
            QMessageBox.warning(self, "ゲーム管理エラー", str(exc))
            return

        self.status_label.setText(
            "スプシへ送信しました: "
            f"送信 {result.sent} 件 / 更新 {result.updated} 件 / "
            f"追記 {result.appended} 件 / 失敗 {result.failed} 件"
        )

    def _game_info_service(self) -> GspreadService:
        config = ConfigLoader().load()
        return GspreadService(
            cert_file_path=config.log_handler.cert_file_path,
            sheet_key=config.game_info.sheet_key,
            sheet_gid=config.game_info.sheet_gid,
        )

    def _push_local_games(self, service: GspreadService) -> GameCatalogPushResult:
        remote_records = service.get_all_records()
        remote_ids = {
            str(record.get("id", "")).strip()
            for record in remote_records
            if str(record.get("id", "")).strip()
        }

        updated = 0
        appended = 0
        failed = 0
        local_records = self.game_store.spreadsheet_records()
        for values in local_records:
            game_id = str(values[0]).strip()
            if not game_id:
                failed += 1
                continue
            if game_id in remote_ids:
                success = service.update_row_by_key("id", game_id, values)
                if success:
                    updated += 1
                else:
                    failed += 1
                continue
            success = service.append_row(values)
            if success:
                appended += 1
                remote_ids.add(game_id)
            else:
                failed += 1

        return GameCatalogPushResult(
            sent=len(local_records),
            updated=updated,
            appended=appended,
            failed=failed,
            total=len(self.game_store.load_games()),
        )
