"""MainWindow context-menu controller."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Sequence

from PySide6.QtWidgets import QMenu, QWidget


class MainWindowContextMenuController:
    """Builds and handles the main-window right-click menu."""

    def __init__(
        self,
        *,
        parent_widget: Optional[QWidget],
        display_modes: Sequence[str],
        display_mode_provider: Callable[[], str],
        set_display_mode: Callable[[str], None],
        open_manual_record_dialog: Callable[[], None],
        open_report_dialog: Callable[[], None],
        open_game_catalog_dialog: Callable[[], None],
        open_settings_dialog: Callable[[], None],
        quit_application: Callable[[], None],
    ) -> None:
        self.parent_widget = parent_widget
        self.display_modes = display_modes
        self.display_mode_provider = display_mode_provider
        self.set_display_mode = set_display_mode
        self.open_manual_record_dialog = open_manual_record_dialog
        self.open_report_dialog = open_report_dialog
        self.open_game_catalog_dialog = open_game_catalog_dialog
        self.open_settings_dialog = open_settings_dialog
        self.quit_application = quit_application

    def show_context_menu(self, event: object) -> None:
        menu = QMenu(self.parent_widget)
        mode_actions = self.add_display_mode_menu(menu)
        manual_record_action = menu.addAction("\u624b\u5165\u529b\u3067\u8a18\u9332")
        report_action = menu.addAction("\u30ec\u30dd\u30fc\u30c8")
        game_catalog_action = menu.addAction("\u30b2\u30fc\u30e0\u7ba1\u7406")
        settings_action = menu.addAction("\u8a2d\u5b9a")
        exit_action = menu.addAction("\u7d42\u4e86")

        position_getter = getattr(event, "globalPosition", None)
        if callable(position_getter):
            position = position_getter().toPoint()
        else:
            position = event.globalPos()

        selected_action = menu.exec(position)
        self.handle_context_menu_selection(
            selected_action,
            manual_record_action=manual_record_action,
            report_action=report_action,
            game_catalog_action=game_catalog_action,
            settings_action=settings_action,
            exit_action=exit_action,
            mode_actions=mode_actions,
        )

    def add_display_mode_menu(self, menu: QMenu) -> Dict[str, object]:
        size_menu = menu.addMenu("\u30b5\u30a4\u30ba")
        mode_actions: Dict[str, object] = {}
        current_mode = self.display_mode_provider()
        for mode in self.display_modes:
            action = size_menu.addAction(mode)
            set_checkable = getattr(action, "setCheckable", None)
            if callable(set_checkable):
                set_checkable(True)
            set_checked = getattr(action, "setChecked", None)
            if callable(set_checked):
                set_checked(mode == current_mode)
            mode_actions[mode] = action
        return mode_actions

    def handle_context_menu_selection(
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
        if mode_actions:
            for mode, action in mode_actions.items():
                if selected_action is action:
                    self.set_display_mode(mode)
                    return
        if selected_action is manual_record_action:
            self.open_manual_record_dialog()
        elif selected_action is report_action:
            self.open_report_dialog()
        elif selected_action is game_catalog_action:
            self.open_game_catalog_dialog()
        elif selected_action is settings_action:
            self.open_settings_dialog()
        elif selected_action is exit_action:
            self.quit_application()
