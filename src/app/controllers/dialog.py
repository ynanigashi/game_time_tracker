"""Dialog orchestration for MainWindow."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from src.app.dialog_state import DialogRefState


class MainWindowDialogController:
    """Owns non-modal dialogs and dialog-driven refresh flows."""

    def __init__(
        self,
        owner: "MainWindow",
        *,
        report_dialog_cls: Callable[..., object],
        manual_record_dialog_cls: Callable[..., object],
        game_catalog_dialog_cls: Callable[..., object],
        settings_dialog_cls: Callable[..., object],
        state: DialogRefState,
    ) -> None:
        self.owner = owner
        self.report_dialog_cls = report_dialog_cls
        self.manual_record_dialog_cls = manual_record_dialog_cls
        self.game_catalog_dialog_cls = game_catalog_dialog_cls
        self.settings_dialog_cls = settings_dialog_cls
        self.state = state

    def initialize_report_button(self) -> None:
        button = self.owner._get_report_button()
        if button is None:
            return

        if self.state.report_button_connected:
            try:
                button.clicked.disconnect(self.owner._open_report_dialog)
            except (TypeError, RuntimeError):
                pass
        button.clicked.connect(self.owner._open_report_dialog)
        self.state.report_button_connected = True

    def initialize_manual_record_button(self) -> None:
        button = self.owner._get_manual_record_button()
        if button is None:
            return

        if self.state.manual_record_button_connected:
            try:
                button.clicked.disconnect(self.owner._open_manual_record_dialog)
            except (TypeError, RuntimeError):
                pass
        button.clicked.connect(self.owner._open_manual_record_dialog)
        self.state.manual_record_button_connected = True

    def open_report_dialog(self) -> None:
        if not hasattr(self.owner, "recorder"):
            return

        dialog = self.state.report_dialog
        if dialog is None or not bool(getattr(dialog, "isVisible", lambda: False)()):
            dialog = self.report_dialog_cls(self.owner.recorder.log_handler, self.owner)
            self.state.report_dialog = dialog

        self._show_dialog(dialog)

    def open_manual_record_dialog(self) -> None:
        if not hasattr(self.owner, "recorder"):
            return

        dialog = self.get_or_create_manual_record_dialog()
        self._show_dialog(dialog)

    def get_or_create_manual_record_dialog(self) -> object:
        dialog = self.state.manual_record_dialog
        if dialog is None or not bool(getattr(dialog, "isVisible", lambda: False)()):
            dialog = self.manual_record_dialog_cls(
                self.owner,
                on_save=self.owner._save_manual_record,
                games=self.owner.games,
            )
            self.state.manual_record_dialog = dialog
        else:
            dialog.set_games(self.owner.games)
        return dialog

    def save_manual_record(self, record: object) -> bool:
        recorded_seconds = self.owner.recorder.record_with_times(
            record.game,
            record.start_time,
            record.end_time,
        )
        if recorded_seconds is None:
            self.owner._set_status(
                f"{record.game.game_title}縺ｮ謇句・蜉幄ｨ倬鹸繧剃ｿ晏ｭ倥〒縺阪∪縺帙ｓ縺ｧ縺励◆"
            )
            return False

        self.refresh_after_manual_record()
        self.owner._set_status(
            f"{record.game.game_title}縺ｮ繝励Ξ繧､譎る俣繧呈焔蜈･蜉帙〒險倬鹸縺励∪縺励◆"
        )
        return True

    def refresh_after_manual_record(self) -> None:
        self.reload_today_stats()
        now = datetime.now()
        total_seconds = self.owner._update_today_totals(
            self.owner.active_games_cache,
            now,
        )
        self.owner._update_today_games_list(now)
        self.owner._update_overtime_alert(total_seconds)
        self.owner._sync_overlay()

    def reload_today_stats(self) -> None:
        game_minutes, completed_seconds = self.owner.recorder.log_handler.get_today_stats()
        self.owner.daily_stats.today_game_minutes_cache = game_minutes
        self.owner.daily_stats.today_completed_seconds = completed_seconds
        self.owner.daily_stats.last_today_games_content = ""

    def open_settings_dialog(self) -> None:
        dialog = self.state.settings_dialog
        if dialog is None or not bool(getattr(dialog, "isVisible", lambda: False)()):
            dialog = self.settings_dialog_cls(self.owner, on_saved=self.owner._on_settings_saved)
            self.state.settings_dialog = dialog

        self._show_dialog(dialog)

    def open_game_catalog_dialog(self, *, initial_window_title: str = "") -> None:
        dialog = self.state.game_catalog_dialog
        created_dialog = False
        if dialog is None or not bool(getattr(dialog, "isVisible", lambda: False)()):
            dialog = self.game_catalog_dialog_cls(
                self.owner,
                on_saved=self.owner._on_game_catalog_saved,
            )
            self.state.game_catalog_dialog = dialog
            created_dialog = True

        dialog.show()

        if created_dialog:
            sync_on_open = getattr(dialog, "sync_on_open", None)
            if callable(sync_on_open):
                sync_on_open()

        if initial_window_title:
            prepare = getattr(dialog, "prepare_new_game", None)
            if callable(prepare):
                prepare(window_title=initial_window_title)

        dialog.raise_()
        dialog.activateWindow()

    def on_game_catalog_saved(self) -> None:
        self.owner._set_status("\u30b2\u30fc\u30e0\u60c5\u5831\u3092\u4fdd\u5b58\u3057\u307e\u3057\u305f\u3002")
        self.owner._init_components()

    def on_settings_saved(self) -> None:
        self.owner.setDisabled(False)
        self.owner._set_status("\u8a2d\u5b9a\u3092\u4fdd\u5b58\u3057\u307e\u3057\u305f\u3002")
        self.owner._init_components()

    @staticmethod
    def _show_dialog(dialog: object) -> None:
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
