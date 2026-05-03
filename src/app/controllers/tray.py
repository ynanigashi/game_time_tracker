"""System tray controller for MainWindow."""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from src.infra.runtime_paths import runtime_path
from src.app.tray_state import TrayActionState

logger = logging.getLogger(__name__)


class MainWindowTrayController:
    """Owns tray icon/menu creation and tray-driven window actions."""

    def __init__(
        self,
        owner: "MainWindow",
        *,
        base_title: str,
        action_state: TrayActionState,
        show_main_window: Callable[[], None] = lambda: None,
        hide_main_window: Callable[[], None] = lambda: None,
        set_tray_overlay_enabled: Callable[[bool], None] = lambda _enabled: None,
        set_startup_window_visible: Callable[[bool], None] = lambda _visible: None,
        open_manual_record_dialog: Callable[[], None] = lambda: None,
        open_report_dialog: Callable[[], None] = lambda: None,
        open_game_catalog_dialog: Callable[[], None] = lambda: None,
        open_settings_dialog: Callable[[], None] = lambda: None,
        quit_application: Callable[[], None] = lambda: None,
        sync_tray_window_actions_callback: Callable[[], None] = lambda: None,
        save_window_state: Callable[[], None] = lambda: None,
        sync_overlay: Callable[[], None] = lambda: None,
        set_force_startup_window_visible: Callable[[bool], None] = lambda _visible: None,
        process_pending_ui_events_callback: Callable[[], None] = lambda: None,
        align_today_display_to_overlay_position_callback: Callable[[], None] = (
            lambda: None
        ),
        today_time_display_provider: Callable[[], object] = lambda: None,
        set_quitting: Callable[[bool], None] = lambda _quitting: None,
        record_playing_games_before_close: Callable[[], None] = lambda: None,
        close_overlay: Callable[[], None] = lambda: None,
    ) -> None:
        self.owner = owner
        self.base_title = base_title
        self.action_state = action_state
        self.show_main_window_callback = show_main_window
        self.hide_main_window_callback = hide_main_window
        self.set_tray_overlay_enabled_callback = set_tray_overlay_enabled
        self.set_startup_window_visible_callback = set_startup_window_visible
        self.open_manual_record_dialog_callback = open_manual_record_dialog
        self.open_report_dialog_callback = open_report_dialog
        self.open_game_catalog_dialog_callback = open_game_catalog_dialog
        self.open_settings_dialog_callback = open_settings_dialog
        self.quit_application_callback = quit_application
        self.sync_tray_window_actions_callback = sync_tray_window_actions_callback
        self.save_window_state = save_window_state
        self.sync_overlay = sync_overlay
        self.set_force_startup_window_visible = set_force_startup_window_visible
        self.process_pending_ui_events_callback = process_pending_ui_events_callback
        self.align_today_display_to_overlay_position_callback = (
            align_today_display_to_overlay_position_callback
        )
        self.today_time_display_provider = today_time_display_provider
        self.set_quitting = set_quitting
        self.record_playing_games_before_close = record_playing_games_before_close
        self.close_overlay = close_overlay

    def initialize_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("system tray is not available")
            self.set_force_startup_window_visible(True)
            return

        tray_icon = QSystemTrayIcon(self.create_tray_icon(), self.owner)
        tray_icon.setToolTip(self.base_title)
        tray_icon.setContextMenu(self.build_tray_menu())
        tray_icon.show()
        self.owner.tray_icon = tray_icon

    def create_tray_icon(self) -> QIcon:
        icon_path = runtime_path("assets", "tray_icon.ico")
        if icon_path.exists():
            return QIcon(str(icon_path))

        try:
            style = QApplication.style()
            standard_pixmap = getattr(
                getattr(QStyle, "StandardPixmap", object),
                "SP_ComputerIcon",
                None,
            )
            if standard_pixmap is not None:
                return style.standardIcon(standard_pixmap)
        except Exception:
            logger.debug("failed to create standard tray icon", exc_info=True)
        return QIcon()

    def build_tray_menu(self) -> QMenu:
        menu = QMenu(self.owner)
        show_action = menu.addAction("\u30a6\u30a3\u30f3\u30c9\u30a6\u3092\u8868\u793a")
        hide_action = menu.addAction("\u30a6\u30a3\u30f3\u30c9\u30a6\u3092\u975e\u8868\u793a")
        overlay_action = menu.addAction("\u30aa\u30fc\u30d0\u30fc\u30ec\u30a4\u8868\u793a")
        overlay_action.setCheckable(True)
        overlay_action.setChecked(bool(getattr(self.owner, "tray_overlay_enabled", False)))

        startup_menu = menu.addMenu("\u8d77\u52d5\u6642")
        startup_show_action = startup_menu.addAction("\u30a6\u30a3\u30f3\u30c9\u30a6\u3092\u8868\u793a")
        startup_hide_action = startup_menu.addAction("\u30a6\u30a3\u30f3\u30c9\u30a6\u3092\u975e\u8868\u793a")
        for action in (startup_show_action, startup_hide_action):
            action.setCheckable(True)
        startup_show_action.setChecked(
            bool(getattr(self.owner, "startup_window_visible", False))
        )
        startup_hide_action.setChecked(
            not bool(getattr(self.owner, "startup_window_visible", False))
        )

        manual_record_action = menu.addAction("\u624b\u5165\u529b\u3067\u8a18\u9332")
        report_action = menu.addAction("\u30ec\u30dd\u30fc\u30c8")
        game_catalog_action = menu.addAction("\u30b2\u30fc\u30e0\u7ba1\u7406")
        settings_action = menu.addAction("\u8a2d\u5b9a")
        exit_action = menu.addAction("\u7d42\u4e86")

        show_action.triggered.connect(
            lambda _checked=False: self.show_main_window_callback()
        )
        hide_action.triggered.connect(
            lambda _checked=False: self.hide_main_window_callback()
        )
        overlay_action.toggled.connect(self.set_tray_overlay_enabled_callback)
        startup_show_action.triggered.connect(
            lambda _checked=False: self.set_startup_window_visible_callback(True)
        )
        startup_hide_action.triggered.connect(
            lambda _checked=False: self.set_startup_window_visible_callback(False)
        )
        manual_record_action.triggered.connect(
            lambda _checked=False: self.open_manual_record_dialog_callback()
        )
        report_action.triggered.connect(
            lambda _checked=False: self.open_report_dialog_callback()
        )
        game_catalog_action.triggered.connect(
            lambda _checked=False: self.open_game_catalog_dialog_callback()
        )
        settings_action.triggered.connect(
            lambda _checked=False: self.open_settings_dialog_callback()
        )
        exit_action.triggered.connect(lambda _checked=False: self.quit_application_callback())

        self.action_state.show_action = show_action
        self.action_state.hide_action = hide_action
        self.action_state.startup_show_action = startup_show_action
        self.action_state.startup_hide_action = startup_hide_action
        self.action_state.overlay_action = overlay_action
        self.owner.tray_menu = menu
        self.sync_tray_window_actions()

        about_to_show = getattr(menu, "aboutToShow", None)
        if about_to_show is not None:
            try:
                about_to_show.connect(self.sync_tray_window_actions_callback)
            except Exception:
                logger.debug("failed to connect tray menu refresh", exc_info=True)
        return menu

    def show_main_window_from_tray(self) -> None:
        self.owner.show()
        self.process_pending_ui_events_callback()
        self.align_today_display_to_overlay_position_callback()
        self.process_pending_ui_events_callback()
        self.align_today_display_to_overlay_position_callback()
        self.owner.raise_()
        self.owner.activateWindow()
        self.sync_tray_window_actions_callback()
        self.sync_overlay()

    @staticmethod
    def process_pending_ui_events() -> None:
        try:
            QApplication.processEvents()
        except Exception:
            logger.debug("failed to process pending UI events", exc_info=True)

    def align_today_display_to_overlay_position(self) -> None:
        overlay_position = getattr(self.owner, "overlay_position", None)
        if overlay_position is None:
            return
        target = self.today_time_display_provider()
        if target is None:
            return
        try:
            top_left = target.mapToGlobal(target.rect().topLeft())
            geometry = self.owner.geometry()
            self.owner.move(
                int(geometry.x()) + int(overlay_position[0]) - int(top_left.x()),
                int(geometry.y()) + int(overlay_position[1]) - int(top_left.y()),
            )
        except Exception:
            logger.debug("failed to align main window to overlay position", exc_info=True)

    def hide_main_window_to_tray(self) -> None:
        self.save_window_state()
        self.owner.hide()
        self.sync_tray_window_actions()
        self.sync_overlay()

    def sync_tray_window_actions(self) -> None:
        is_window_visible = bool(getattr(self.owner, "isVisible", lambda: False)())
        show_action = self.action_state.show_action
        hide_action = self.action_state.hide_action
        if show_action is not None:
            set_visible = getattr(show_action, "setVisible", None)
            if callable(set_visible):
                set_visible(not is_window_visible)
        if hide_action is not None:
            set_visible = getattr(hide_action, "setVisible", None)
            if callable(set_visible):
                set_visible(is_window_visible)

    def set_startup_window_visible(self, visible: bool) -> None:
        self.owner.startup_window_visible = bool(visible)
        show_action = self.action_state.startup_show_action
        hide_action = self.action_state.startup_hide_action
        if show_action is not None:
            show_action.setChecked(self.owner.startup_window_visible)
        if hide_action is not None:
            hide_action.setChecked(not self.owner.startup_window_visible)
        self.save_window_state()

    def set_tray_overlay_enabled(self, enabled: bool) -> None:
        self.owner.tray_overlay_enabled = bool(enabled)
        self.save_window_state()
        self.sync_overlay()

    def quit_application(self) -> None:
        self.set_quitting(True)
        self.record_playing_games_before_close()
        self.save_window_state()
        self.close_overlay()
        tray_icon = getattr(self.owner, "tray_icon", None)
        if tray_icon is not None:
            tray_icon.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def should_show_window_on_startup(self) -> bool:
        return bool(
            getattr(self.owner, "_force_startup_window_visible", False)
            or getattr(self.owner, "startup_window_visible", False)
        )
