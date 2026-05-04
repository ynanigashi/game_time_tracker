"""MainWindow action methods installed outside the QWidget subclass."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, Sequence, cast

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel, QMenu, QPushButton, QWidget

from src.app.controllers import (
    MainWindowBootstrapError,
    OvertimeAlertTracker,
    TodayTimeOverlayWindow,
)
from src.app.main_constants import BASE_TITLE
from src.core.adapters import Messages
from src.core.models import GameEntry
from src.core.window_state import DISPLAY_MODES
from src.ui.manual_record_dialog import ManualPlayRecord, ManualRecordDialog


def _main_module() -> object:
    from src.app import main as main_module

    return main_module


class MainWindowActionMethods:
    """Runtime, dialog, overlay, alert, and display actions for MainWindow."""

    def _record_playing_games_before_close(self) -> None:
        for game in self._iter_recordable_games():
            self.recorder.record(game)

    def _iter_recordable_games(self) -> Sequence[GameEntry]:
        return [
            game
            for game in getattr(self, "games", [])
            if game.is_playing and game.start_time
        ]

    def _start_timer(
        self,
        interval_seconds: float,
        callback: object,
    ) -> QTimer:
        return self._get_loop_controller().start_timer(self, interval_seconds, callback)

    def _disable_with_status(self, message: str) -> None:
        self._set_status(message)
        self.setDisabled(True)

    def _init_components(self) -> None:
        try:
            result = self._get_bootstrapper().bootstrap(window_title=self.windowTitle())
        except MainWindowBootstrapError as e:
            if e.log_message:
                _main_module().logger.error(e.log_message)
            if getattr(e, "open_settings", False):
                self._force_startup_window_visible = True
                self._set_status(e.status_message)
                alert_message = getattr(e, "alert_message", None)
                if alert_message:
                    _main_module().QMessageBox.warning(
                        self,
                        getattr(e, "alert_title", "設定エラー"),
                        alert_message,
                    )
                self._open_settings_dialog()
                return
            if getattr(e, "open_game_catalog", False):
                self._force_startup_window_visible = True
                self._set_status(e.status_message)
                self._open_game_catalog_dialog()
                return
            self._force_startup_window_visible = True
            self._disable_with_status(e.status_message)
            return

        self._apply_bootstrap_result(result)
        self._initialize_overtime_alert_toggle()
        self._initialize_report_button()
        self._initialize_manual_record_button()
        self._apply_display_mode()
        self._apply_mode_geometry()
        self._set_status(Messages.NO_GAME_PLAYING)
        self._initialize_overlay()

    def _save_window_state(self) -> None:
        self._get_state_controller().save(
            self.geometry(),
            self.display_mode,
            self.mode_sizes,
            self._is_overtime_alert_enabled(),
            startup_window_visible=bool(getattr(self, "startup_window_visible", False)),
            tray_overlay_enabled=bool(getattr(self, "tray_overlay_enabled", False)),
            overlay_position=getattr(self, "overlay_position", None),
        )

    def _set_status(self, message: str) -> None:
        title = f"{BASE_TITLE} - {message}" if message else BASE_TITLE
        self.setWindowTitle(title)
        if hasattr(self, "scanner"):
            self.scanner.excluded_titles.add(title)

    def _initialize_overlay(self) -> None:
        self._get_overlay_controller().initialize_overlay()

    def _is_overtime_alert_enabled(self) -> bool:
        return self._get_overtime_alert_controller().is_enabled()

    def _set_overtime_alert_enabled(self, enabled: bool) -> None:
        self._get_overtime_alert_controller().set_enabled(enabled)

    def _get_overtime_alert_tracker(self) -> OvertimeAlertTracker:
        return self._get_overtime_alert_controller().get_tracker()

    def _get_overtime_alert_toggle(self) -> Optional[QPushButton]:
        return self.w.overtime_alert_toggle

    def _get_report_button(self) -> Optional[QPushButton]:
        return getattr(self.w, "report_button", None)

    def _get_manual_record_button(self) -> Optional[QPushButton]:
        return getattr(self.w, "manual_record_button", None)

    def _initialize_overtime_alert_toggle(self) -> None:
        self._get_overtime_alert_controller().initialize_toggle()

    def _initialize_report_button(self) -> None:
        self._get_dialog_controller().initialize_report_button()

    def _initialize_manual_record_button(self) -> None:
        self._get_dialog_controller().initialize_manual_record_button()

    def _open_report_dialog(self) -> None:
        self._get_dialog_controller().open_report_dialog()

    def _open_manual_record_dialog(self) -> None:
        self._get_dialog_controller().open_manual_record_dialog()

    def _get_or_create_manual_record_dialog(self) -> ManualRecordDialog:
        return cast(
            ManualRecordDialog,
            self._get_dialog_controller().get_or_create_manual_record_dialog(),
        )

    def _save_manual_record(self, record: ManualPlayRecord) -> bool:
        return self._get_dialog_controller().save_manual_record(record)

    def _refresh_after_manual_record(self) -> None:
        self._get_dialog_controller().refresh_after_manual_record()

    def _reload_today_stats(self) -> None:
        self._get_dialog_controller().reload_today_stats()

    def _set_today_stats_cache(
        self,
        game_minutes: Dict[str, float],
        completed_seconds: float,
    ) -> None:
        self.daily_stats.today_game_minutes_cache = game_minutes
        self.daily_stats.today_completed_seconds = completed_seconds
        self.daily_stats.last_today_games_content = ""

    def _open_settings_dialog(self) -> None:
        self._get_dialog_controller().open_settings_dialog()

    def _open_game_catalog_dialog(self, *, initial_window_title: str = "") -> None:
        self._get_dialog_controller().open_game_catalog_dialog(
            initial_window_title=initial_window_title
        )

    def _on_game_catalog_saved(self) -> None:
        self._get_dialog_controller().on_game_catalog_saved()

    def _on_settings_saved(self) -> None:
        self._get_dialog_controller().on_settings_saved()

    def _on_overtime_alert_toggled(self, checked: bool) -> None:
        self._get_overtime_alert_controller().on_toggled(checked)

    def _prime_overtime_alert_progress(self, total_seconds: float) -> None:
        self._get_overtime_alert_controller().prime_progress(total_seconds)

    def _emit_overtime_alert(self, threshold_minutes: int) -> None:
        self._get_overtime_alert_controller().emit_alert(threshold_minutes)

    def _update_overtime_alert(self, total_seconds: float) -> None:
        self._get_overtime_alert_controller().update_alert(total_seconds)

    def _get_overlay_window(self) -> Optional[TodayTimeOverlayWindow]:
        return self.overlay_window

    def _get_today_time_display(self) -> Optional[QLabel]:
        return self.w.today_time_display

    def _refresh_overlay_time(self) -> None:
        self._get_overlay_controller().refresh_overlay_time()

    def _sync_overlay_geometry(self) -> None:
        self._get_overlay_controller().sync_overlay_geometry()

    def _should_show_overlay(self) -> bool:
        return self._get_overlay_controller().should_show_overlay()

    def _sync_overlay_visibility(self) -> None:
        self._get_overlay_controller().sync_overlay_visibility()

    def _sync_overlay(self) -> None:
        self._get_overlay_controller().sync_overlay()

    def _close_overlay(self) -> None:
        self._get_overlay_controller().close_overlay()

    def _apply_mode_geometry(self) -> None:
        self._get_display_controller().apply_mode_geometry(
            self,
            self.display_mode,
            self.mode_sizes,
        )

    def _apply_display_mode(self) -> None:
        self._get_display_controller().apply_display_mode(
            display_mode=self.display_mode,
            widgets=self.w,
            set_widget_visibility=self._set_widget_visibility,
            set_widget_with_height=self._set_widget_with_height,
            apply_mode_geometry=self._apply_mode_geometry,
        )

    def _set_widget_visibility(self, widget: QWidget, visible: bool) -> None:
        self._get_display_controller().set_widget_visibility(widget, visible)

    def _set_widget_with_height(
        self,
        widget: QWidget,
        visible: bool,
        *,
        min_height: int,
        max_height: int,
    ) -> None:
        self._get_display_controller().set_widget_with_height(
            widget,
            visible,
            min_height=min_height,
            max_height=max_height,
        )

    @staticmethod
    def _should_cycle_display_mode(event: QMouseEvent) -> bool:
        return event.button() == Qt.MouseButton.LeftButton

    @staticmethod
    def _should_show_context_menu(event: QMouseEvent) -> bool:
        return event.button() == Qt.MouseButton.RightButton

    def _show_context_menu(self, event: QMouseEvent) -> None:
        self._get_context_menu_controller().show_context_menu(event)

    def _add_display_mode_menu(self, menu: QMenu) -> Dict[str, object]:
        return self._get_context_menu_controller().add_display_mode_menu(menu)

    def _handle_context_menu_selection(
        self,
        selected_action: object,
        *,
        report_action: object,
        settings_action: object,
        exit_action: object,
        game_catalog_action: object = None,
        mode_actions: Optional[Dict[str, object]] = None,
        manual_record_action: object = None,
    ) -> None:
        self._get_context_menu_controller().handle_context_menu_selection(
            selected_action,
            report_action=report_action,
            settings_action=settings_action,
            exit_action=exit_action,
            game_catalog_action=game_catalog_action,
            mode_actions=mode_actions,
            manual_record_action=manual_record_action,
        )

    def _set_display_mode(self, display_mode: str) -> None:
        if display_mode not in DISPLAY_MODES:
            return
        if self.display_mode == display_mode:
            return
        self.display_mode = display_mode
        self._apply_display_mode()
        self._save_window_state()

    def _cycle_display_mode(self) -> None:
        self.display_mode = self._get_display_controller().next_display_mode(
            self.display_mode
        )
        self._apply_display_mode()
        self._save_window_state()

    def _record_current_mode_size(self) -> None:
        self._get_state_controller().record_resize(
            self.mode_sizes,
            self.display_mode,
            self.width(),
            self.height(),
        )


def install_main_window_action_methods(target_cls: type) -> None:
    """Install MainWindow action methods."""
    for name, descriptor in MainWindowActionMethods.__dict__.items():
        if name.startswith("__"):
            continue
        setattr(target_cls, name, descriptor)
