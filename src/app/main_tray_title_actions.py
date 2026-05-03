"""Tray and window-title action proxies for MainWindow."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMenu, QWidget

from src.app.controllers import MainWindowTitleController, MainWindowTrayController


class MainWindowTrayTitleActions:
    """Compatibility methods that delegate tray and title-list work to controllers."""

    def _initialize_tray_icon(self) -> None:
        """Create the tray icon and context menu used as the app's home."""
        self._get_tray_controller().initialize_tray_icon()

    def _build_tray_menu(self) -> QMenu:
        return self._get_tray_controller().build_tray_menu()

    def _show_main_window_from_tray(self) -> None:
        self._get_tray_controller().show_main_window_from_tray()

    @staticmethod
    def _process_pending_ui_events() -> None:
        MainWindowTrayController.process_pending_ui_events()

    def _align_today_display_to_overlay_position(self) -> None:
        self._get_tray_controller().align_today_display_to_overlay_position()

    def _hide_main_window_to_tray(self) -> None:
        self._get_tray_controller().hide_main_window_to_tray()

    def _sync_tray_window_actions(self) -> None:
        self._get_tray_controller().sync_tray_window_actions()

    def _set_startup_window_visible(self, visible: bool) -> None:
        self._get_tray_controller().set_startup_window_visible(visible)

    def _set_tray_overlay_enabled(self, enabled: bool) -> None:
        self._get_tray_controller().set_tray_overlay_enabled(enabled)

    def _quit_application(self) -> None:
        self._get_tray_controller().quit_application()

    def should_show_window_on_startup(self) -> bool:
        return self._get_tray_controller().should_show_window_on_startup()

    def _get_window_list_widget(self) -> Optional[QWidget]:
        """Return the current window-title list widget."""
        return self._get_window_title_controller().get_window_list_widget()

    def _initialize_window_title_copy(self) -> None:
        """Initialize click-copy and context-menu handling for window titles."""
        self._get_window_title_controller().initialize_window_title_copy()

    def _initialize_window_title_context_menu(self, window_list: QWidget) -> None:
        self._get_window_title_controller().initialize_window_title_context_menu(window_list)

    def _on_window_title_item_clicked(self, item: object) -> None:
        """Copy a clicked window title to the clipboard."""
        self._get_window_title_controller().on_window_title_item_clicked(item)

    def _show_window_title_context_menu(self, position: object) -> None:
        self._get_window_title_controller().show_window_title_context_menu(position)

    @staticmethod
    def _window_title_item_at(window_list: QWidget, position: object) -> object:
        return MainWindowTitleController.window_title_item_at(window_list, position)

    @staticmethod
    def _text_from_window_title_item(item: object) -> str:
        return MainWindowTitleController.text_from_window_title_item(item)

    def _copy_text_to_clipboard(self, text: str) -> None:
        """Copy text to the clipboard."""
        self._get_window_title_controller().copy_text_to_clipboard(text)
