"""Async log edit/delete controller for the report dialog."""

from __future__ import annotations

import logging
from typing import Callable, List

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from src.ui.report_log_operation_state import ReportLogOperationState

logger = logging.getLogger(__name__)


class ReportLogOperationController:
    """Run play-log edit/delete operations without blocking the dialog."""

    def __init__(
        self,
        owner: object,
        state: ReportLogOperationState,
        *,
        log_tab: int,
        set_debug_message: Callable[..., None],
        mark_report_data_changed: Callable[[], None],
        mark_tab_clean: Callable[[int], None],
    ) -> None:
        self.owner = owner
        self.state = state
        self.log_tab = int(log_tab)
        self.set_debug_message = set_debug_message
        self.mark_report_data_changed = mark_report_data_changed
        self.mark_tab_clean = mark_tab_clean

    def start_log_edit(self, record_id: str, values: List[object]) -> None:
        update_record = getattr(self.owner.log_handler, "update_record", None)
        if not callable(update_record):
            QMessageBox.warning(
                self.owner,
                "ログ編集エラー",
                "このログハンドラは編集に対応していません",
            )
            return

        self.start_log_operation(
            busy_message="ログ編集を保存中...",
            worker=lambda: update_record(record_id, values),
            finish_callback=self.finish_log_edit,
        )

    def start_log_delete(self, record_id: str) -> None:
        delete_record = getattr(self.owner.log_handler, "delete_record", None)
        if not callable(delete_record):
            QMessageBox.warning(
                self.owner,
                "ログ削除エラー",
                "このログハンドラは削除に対応していません",
            )
            return

        self.start_log_operation(
            busy_message="ログを削除中...",
            worker=lambda: delete_record(record_id),
            finish_callback=self.finish_log_delete,
        )

    def start_log_operation(
        self,
        *,
        busy_message: str,
        worker: Callable[[], object],
        finish_callback: Callable[[object], None],
    ) -> None:
        future = self.state.future
        if future is not None and not future.done():
            self._set_debug_message("ログ操作中です。完了まで待ってください")
            return

        self.owner.log_edit_button.setEnabled(False)
        self.owner.log_delete_button.setEnabled(False)
        self._set_debug_message(busy_message, process_events=True)
        self.state.finish_callback = finish_callback
        self.state.future = self.state.executor.submit(worker)
        self.state.timer = QTimer(self.owner)
        self.state.timer.setInterval(100)
        self.state.timer.timeout.connect(self.check_log_edit_result)
        self.state.timer.start()

    def check_log_edit_result(self) -> None:
        future = self.state.future
        if future is None or not future.done():
            return

        if self.state.timer is not None:
            self.state.timer.stop()
            self.state.timer.deleteLater()
            self.state.timer = None
        self.state.future = None
        self.owner.log_edit_button.setEnabled(True)
        self.owner.log_delete_button.setEnabled(True)

        try:
            result = future.result()
        except Exception as exc:
            self.state.finish_callback = None
            logger.exception("Failed to complete play log operation")
            QMessageBox.warning(self.owner, "ログ編集エラー", str(exc))
            return

        finish_callback = self.state.finish_callback
        self.state.finish_callback = None
        if finish_callback is not None:
            finish_callback(result)

    def finish_log_edit(self, result: object) -> None:
        if not getattr(result, "local_updated", False):
            QMessageBox.warning(
                self.owner,
                "ログ編集エラー",
                str(getattr(result, "error_message", "") or "ローカルDBの更新に失敗しました"),
            )
            return

        self.mark_report_data_changed()
        self.owner.refresh_logs()
        self.mark_tab_clean(self.log_tab)
        if getattr(result, "spreadsheet_updated", False):
            self._set_debug_message("ログを編集し、スプシにも反映しました")
            return

        error_message = str(getattr(result, "error_message", "") or "")
        if error_message:
            self._set_debug_message(
                f"ログを編集しました。スプシ反映は失敗しました: {error_message}"
            )
        else:
            self._set_debug_message(
                "ログを編集しました。スプシ設定がないためローカルのみ更新しました"
            )

    def finish_log_delete(self, result: object) -> None:
        if not getattr(result, "local_deleted", False):
            QMessageBox.warning(
                self.owner,
                "ログ削除エラー",
                str(getattr(result, "error_message", "") or "ローカルDBの削除に失敗しました"),
            )
            return

        self.mark_report_data_changed()
        self.owner.refresh_logs()
        self.mark_tab_clean(self.log_tab)
        if getattr(result, "spreadsheet_deleted", False):
            self._set_debug_message("ログを削除し、スプシにも反映しました")
            return

        error_message = str(getattr(result, "error_message", "") or "")
        if error_message:
            self._set_debug_message(
                f"ログを削除しました。スプシ反映は失敗しました: {error_message}"
            )
        else:
            self._set_debug_message(
                "ログを削除しました。スプシ設定がないためローカルのみ削除しました"
            )

    def close(self) -> None:
        self.state.shutdown()

    def _set_debug_message(
        self,
        message: str,
        *,
        process_events: bool = False,
    ) -> None:
        self.set_debug_message(message, process_events=process_events)
