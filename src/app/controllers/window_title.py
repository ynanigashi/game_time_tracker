"""Window-title list interactions for MainWindow."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from src.app.window_title_state import WindowTitleState

logger = logging.getLogger(__name__)


class MainWindowTitleController:
    """Handles title-list copy and game-catalog context actions."""

    def __init__(
        self,
        owner: "MainWindow",
        *,
        qmenu_cls: Callable[..., object],
        state: WindowTitleState,
    ) -> None:
        self.owner = owner
        self.qmenu_cls = qmenu_cls
        self.state = state

    def get_window_list_widget(self) -> Optional[QWidget]:
        return getattr(self.owner.w, "window_list", None)

    def initialize_window_title_copy(self) -> None:
        window_list = self.owner._get_window_list_widget()
        if window_list is None:
            return

        if not self.state.copy_connected:
            item_clicked_signal = getattr(window_list, "itemClicked", None)
            if item_clicked_signal is not None:
                try:
                    item_clicked_signal.connect(self.owner._on_window_title_item_clicked)
                    self.state.copy_connected = True
                except Exception:
                    logger.debug(
                        "ウィンドウタイトルクリックシグナルの接続に失敗",
                        exc_info=True,
                    )

        if not self.state.context_menu_connected:
            self.owner._initialize_window_title_context_menu(window_list)

        if self.state.copy_connected or self.state.context_menu_connected:
            set_tooltip = getattr(window_list, "setToolTip", None)
            if callable(set_tooltip):
                set_tooltip("\u30af\u30ea\u30c3\u30af\u3067\u30b3\u30d4\u30fc\u3002\u53f3\u30af\u30ea\u30c3\u30af\u3067\u30b2\u30fc\u30e0\u7ba1\u7406\u306b\u8ffd\u52a0")

    def initialize_window_title_context_menu(self, window_list: QWidget) -> None:
        signal = getattr(window_list, "customContextMenuRequested", None)
        if signal is None:
            return

        context_menu_policy = getattr(
            getattr(Qt, "ContextMenuPolicy", object),
            "CustomContextMenu",
            None,
        )
        if context_menu_policy is None:
            context_menu_policy = getattr(Qt, "CustomContextMenu", None)

        set_policy = getattr(window_list, "setContextMenuPolicy", None)
        if callable(set_policy) and context_menu_policy is not None:
            try:
                set_policy(context_menu_policy)
            except Exception:
                logger.debug("ウィンドウタイトル右クリック設定に失敗", exc_info=True)

        try:
            signal.connect(self.owner._show_window_title_context_menu)
        except Exception:
            logger.debug("ウィンドウタイトル右クリックシグナルの接続に失敗", exc_info=True)
            return
        self.state.context_menu_connected = True

    def on_window_title_item_clicked(self, item: object) -> None:
        if item is None:
            return

        text_getter = getattr(item, "text", None)
        if not callable(text_getter):
            return

        try:
            text = str(text_getter())
        except Exception:
            logger.debug("ウィンドウタイトルテキストの取得に失敗", exc_info=True)
            return

        self.owner._copy_text_to_clipboard(text)

    def show_window_title_context_menu(self, position: object) -> None:
        window_list = self.owner._get_window_list_widget()
        if window_list is None:
            return

        item = self.owner._window_title_item_at(window_list, position)
        title = self.owner._text_from_window_title_item(item)
        if not title:
            return

        menu = self.qmenu_cls(window_list)
        add_action = menu.addAction("\u30b2\u30fc\u30e0\u4e00\u89a7\u306b\u8ffd\u52a0")

        map_to_global = getattr(window_list, "mapToGlobal", None)
        global_position = map_to_global(position) if callable(map_to_global) else position
        selected_action = menu.exec(global_position)
        if selected_action is add_action:
            self.owner._open_game_catalog_dialog(initial_window_title=title)

    @staticmethod
    def window_title_item_at(window_list: QWidget, position: object) -> object:
        item_at = getattr(window_list, "itemAt", None)
        if callable(item_at):
            return item_at(position)
        current_item = getattr(window_list, "currentItem", None)
        if callable(current_item):
            return current_item()
        return None

    @staticmethod
    def text_from_window_title_item(item: object) -> str:
        if item is None:
            return ""
        text_getter = getattr(item, "text", None)
        if not callable(text_getter):
            return ""
        try:
            return str(text_getter()).strip()
        except Exception:
            logger.debug("ウィンドウタイトルテキストの取得に失敗", exc_info=True)
            return ""

    def copy_text_to_clipboard(self, text: str) -> None:
        if not text or not text.strip():
            return

        clipboard_getter = getattr(QApplication, "clipboard", None)
        if not callable(clipboard_getter):
            return

        try:
            clipboard = clipboard_getter()
        except Exception:
            logger.debug("クリップボードの取得に失敗", exc_info=True)
            return
        if clipboard is None:
            return

        set_text = getattr(clipboard, "setText", None)
        if not callable(set_text):
            return

        try:
            set_text(text)
        except Exception:
            logger.debug("クリップボードへのコピーに失敗", exc_info=True)
            return
        self.owner._set_status("\u30a6\u30a3\u30f3\u30c9\u30a6\u30bf\u30a4\u30c8\u30eb\u3092\u30b3\u30d4\u30fc\u3057\u307e\u3057\u305f")
