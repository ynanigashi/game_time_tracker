"""Dialog orchestration for MainWindow."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, Optional

from src.app.dialog_state import DialogRefState


class MainWindowDialogController:
    """Owns non-modal dialogs and dialog-driven refresh flows."""

    def __init__(
        self,
        *,
        parent_widget: object,
        report_dialog_cls: Callable[..., object],
        manual_record_dialog_cls: Callable[..., object],
        game_catalog_dialog_cls: Callable[..., object],
        settings_dialog_cls: Callable[..., object],
        state: DialogRefState,
        has_recorder: Callable[[], bool],
        log_handler_provider: Callable[[], object],
        record_with_times: Callable[[object, datetime, datetime], Optional[float]],
        games_provider: Callable[[], list],
        get_today_stats: Callable[[], tuple[Dict[str, float], float]],
        set_today_stats: Callable[[Dict[str, float], float], None],
        set_disabled: Callable[[bool], None],
        get_report_button: Callable[[], object],
        get_manual_record_button: Callable[[], object],
        open_report_dialog_callback: Callable[[], None],
        open_manual_record_dialog_callback: Callable[[], None],
        set_status: Callable[[str], None],
        active_games_provider: Callable[[], list],
        update_today_totals: Callable[[list, datetime], float],
        update_today_games_list: Callable[[datetime], None],
        update_overtime_alert: Callable[[float], None],
        sync_overlay: Callable[[], None],
        on_settings_saved_callback: Callable[[], None],
        on_game_catalog_saved_callback: Callable[[], None],
        init_components: Callable[[], None],
    ) -> None:
        self.parent_widget = parent_widget
        self.report_dialog_cls = report_dialog_cls
        self.manual_record_dialog_cls = manual_record_dialog_cls
        self.game_catalog_dialog_cls = game_catalog_dialog_cls
        self.settings_dialog_cls = settings_dialog_cls
        self.state = state
        self.has_recorder = has_recorder
        self.log_handler_provider = log_handler_provider
        self.record_with_times = record_with_times
        self.games_provider = games_provider
        self.get_today_stats = get_today_stats
        self.set_today_stats = set_today_stats
        self.set_disabled = set_disabled
        self.get_report_button = get_report_button
        self.get_manual_record_button = get_manual_record_button
        self.open_report_dialog_callback = open_report_dialog_callback
        self.open_manual_record_dialog_callback = open_manual_record_dialog_callback
        self.set_status = set_status
        self.active_games_provider = active_games_provider
        self.update_today_totals = update_today_totals
        self.update_today_games_list = update_today_games_list
        self.update_overtime_alert = update_overtime_alert
        self.sync_overlay = sync_overlay
        self.on_settings_saved_callback = on_settings_saved_callback
        self.on_game_catalog_saved_callback = on_game_catalog_saved_callback
        self.init_components = init_components

    def initialize_report_button(self) -> None:
        button = self.get_report_button()
        if button is None:
            return

        if self.state.report_button_connected:
            try:
                button.clicked.disconnect(self.open_report_dialog_callback)
            except (TypeError, RuntimeError):
                pass
        button.clicked.connect(self.open_report_dialog_callback)
        self.state.report_button_connected = True

    def initialize_manual_record_button(self) -> None:
        button = self.get_manual_record_button()
        if button is None:
            return

        if self.state.manual_record_button_connected:
            try:
                button.clicked.disconnect(self.open_manual_record_dialog_callback)
            except (TypeError, RuntimeError):
                pass
        button.clicked.connect(self.open_manual_record_dialog_callback)
        self.state.manual_record_button_connected = True

    def open_report_dialog(self) -> None:
        if not self.has_recorder():
            return

        dialog = self.state.report_dialog
        if dialog is None or not bool(getattr(dialog, "isVisible", lambda: False)()):
            dialog = self.report_dialog_cls(
                self.log_handler_provider(),
                self.parent_widget,
            )
            self.state.report_dialog = dialog

        self._show_dialog(dialog)

    def open_manual_record_dialog(self) -> None:
        if not self.has_recorder():
            return

        dialog = self.get_or_create_manual_record_dialog()
        self._show_dialog(dialog)

    def get_or_create_manual_record_dialog(self) -> object:
        dialog = self.state.manual_record_dialog
        if dialog is None or not bool(getattr(dialog, "isVisible", lambda: False)()):
            dialog = self.manual_record_dialog_cls(
                self.parent_widget,
                on_save=self.save_manual_record,
                games=self.games_provider(),
            )
            self.state.manual_record_dialog = dialog
        else:
            dialog.set_games(self.games_provider())
        return dialog

    def save_manual_record(self, record: object) -> bool:
        recorded_seconds = self.record_with_times(
            record.game,
            record.start_time,
            record.end_time,
        )
        if recorded_seconds is None:
            self.set_status(
                f"{record.game.game_title}縺ｮ謇句・蜉幄ｨ倬鹸繧剃ｿ晏ｭ倥〒縺阪∪縺帙ｓ縺ｧ縺励◆"
            )
            return False

        self.refresh_after_manual_record()
        self.set_status(
            f"{record.game.game_title}縺ｮ繝励Ξ繧､譎る俣繧呈焔蜈･蜉帙〒險倬鹸縺励∪縺励◆"
        )
        return True

    def refresh_after_manual_record(self) -> None:
        self.reload_today_stats()
        now = datetime.now()
        total_seconds = self.update_today_totals(self.active_games_provider(), now)
        self.update_today_games_list(now)
        self.update_overtime_alert(total_seconds)
        self.sync_overlay()

    def reload_today_stats(self) -> None:
        game_minutes, completed_seconds = self.get_today_stats()
        self.set_today_stats(game_minutes, completed_seconds)

    def open_settings_dialog(self) -> None:
        dialog = self.state.settings_dialog
        if dialog is None or not bool(getattr(dialog, "isVisible", lambda: False)()):
            dialog = self.settings_dialog_cls(
                self.parent_widget,
                on_saved=self.on_settings_saved_callback,
            )
            self.state.settings_dialog = dialog

        self._show_dialog(dialog)

    def open_game_catalog_dialog(self, *, initial_window_title: str = "") -> None:
        dialog = self.state.game_catalog_dialog
        created_dialog = False
        if dialog is None or not bool(getattr(dialog, "isVisible", lambda: False)()):
            dialog = self.game_catalog_dialog_cls(
                self.parent_widget,
                on_saved=self.on_game_catalog_saved_callback,
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
        self.set_status("\u30b2\u30fc\u30e0\u60c5\u5831\u3092\u4fdd\u5b58\u3057\u307e\u3057\u305f\u3002")
        self.init_components()

    def on_settings_saved(self) -> None:
        self.set_disabled(False)
        self.set_status("\u8a2d\u5b9a\u3092\u4fdd\u5b58\u3057\u307e\u3057\u305f\u3002")
        self.init_components()

    @staticmethod
    def _show_dialog(dialog: object) -> None:
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
