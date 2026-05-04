"""MainWindow overlay controller."""

import logging
import time
from typing import Any, Callable, Optional, Tuple, cast

from PySide6.QtWidgets import QApplication, QWidget

from src.app.overlay_window import (
    OVERLAY_DEFAULT_MARGIN,
    OVERLAY_FALLBACK_HEIGHT,
    OVERLAY_FALLBACK_WIDTH,
    MK_LBUTTON,
    QCursor,
    TodayTimeOverlayWindow,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MOUSEMOVE,
    _WinMsg,
    sys,
)
from src.app.overlay_state import OverlayVisibilityLogState
from src.app.win32_helpers import get_foreground_hwnd

logger = logging.getLogger(__name__)


class MainWindowOverlayController:
    """MainWindow のオーバーレイ表示制御ロジック."""

    def __init__(
        self,
        *,
        overlay_window_provider: Callable[[], object],
        set_overlay_window: Callable[[object], None],
        set_overlay_position: Callable[[Tuple[int, int]], None],
        get_overlay_position: Callable[[], Optional[Tuple[int, int]]],
        today_time_display_provider: Callable[[], object],
        save_window_state: Callable[[], None],
        has_playing_games: Callable[[], bool],
        today_display_cover_state: Optional[Callable[[], Tuple[bool, str]]] = None,
        is_own_window: Optional[Callable[[int], bool]] = None,
        is_main_window_visible: Callable[[], bool],
        is_main_window_active: Callable[[], bool],
        is_active_window_own: Callable[[object], bool],
        window_geometry: Callable[[], object],
        move_window: Callable[[int, int], None],
        get_tray_overlay_enabled: Callable[[], bool],
    ) -> None:
        self.visibility_log_state = OverlayVisibilityLogState()
        self.overlay_window_provider = overlay_window_provider
        self.set_overlay_window = set_overlay_window
        self.set_overlay_position = set_overlay_position
        self.get_overlay_position = get_overlay_position
        self.today_time_display_provider = today_time_display_provider
        self.save_window_state = save_window_state
        self.has_playing_games = has_playing_games
        self.today_display_cover_state = today_display_cover_state
        self.is_own_window = is_own_window
        self.is_main_window_visible = is_main_window_visible
        self.is_main_window_active = is_main_window_active
        self.is_active_window_own = is_active_window_own
        self.window_geometry = window_geometry
        self.move_window = move_window
        self.get_tray_overlay_enabled = get_tray_overlay_enabled

    def initialize_overlay(self) -> None:
        """今日のプレイ時間オーバーレイを初期化する."""
        if self.overlay_window_provider() is not None:
            return

        try:
            overlay_window = TodayTimeOverlayWindow(
                on_moved=self._on_overlay_moved,
                on_dragged=self._on_overlay_dragged,
                on_move_finished=self._save_overlay_position,
            )
            self.set_overlay_window(overlay_window)
            overlay_window.hide()
            self.sync_overlay()
        except Exception as e:
            logger.warning("オーバーレイ初期化に失敗したため無効化します: %s", e)
            self.set_overlay_window(None)

    def _on_overlay_moved(self, x: int, y: int) -> None:
        self.set_overlay_position((int(x), int(y)))

    def _on_overlay_dragged(self, x: int, y: int) -> None:
        if not bool(self.is_main_window_visible()):
            return
        self._move_owner_today_display_to(int(x), int(y))

    def _move_owner_today_display_to(self, x: int, y: int) -> None:
        target = self.today_time_display_provider()
        if target is None:
            return
        try:
            top_left = target.mapToGlobal(target.rect().topLeft())
            geometry = self.window_geometry()
            if geometry is None:
                return
            self.move_window(
                int(geometry.x()) + int(x) - int(top_left.x()),
                int(geometry.y()) + int(y) - int(top_left.y()),
            )
        except Exception:
            logger.debug("メインウィンドウ位置の同期に失敗", exc_info=True)

    def _save_overlay_position(self) -> None:
        self.save_window_state()

    def refresh_overlay_time(self) -> None:
        """オーバーレイの時刻表示を更新する."""
        overlay_window = self.overlay_window_provider()
        today_time_display = self.today_time_display_provider()
        if overlay_window is None or today_time_display is None:
            return
        overlay_window.set_today_text(today_time_display.text())

    def sync_overlay_geometry(self) -> None:
        """Apply the overlay position for the current main-window state."""
        overlay_window = self.overlay_window_provider()
        if overlay_window is None:
            return
        is_dragging = getattr(overlay_window, "is_dragging", None)
        if callable(is_dragging) and is_dragging() is True:
            return

        try:
            if bool(self.is_main_window_visible()):
                target = self.today_time_display_provider()
                if target is None:
                    return
                top_left = target.mapToGlobal(target.rect().topLeft())
                width = max(1, int(target.width()))
                height = max(1, int(target.height()))
                self._set_overlay_geometry(
                    overlay_window,
                    int(top_left.x()),
                    int(top_left.y()),
                    width,
                    height,
                    notify_moved=False,
                )
                return

            overlay_width = max(1, int(getattr(overlay_window, "width", lambda: OVERLAY_FALLBACK_WIDTH)()))
            overlay_height = max(1, int(getattr(overlay_window, "height", lambda: OVERLAY_FALLBACK_HEIGHT)()))
            manual_position = self.get_overlay_position()
            if manual_position is not None:
                x, y = manual_position
                x, y = self._clamp_overlay_position(int(x), int(y), overlay_width, overlay_height)
                self._set_overlay_geometry(
                    overlay_window,
                    int(x),
                    int(y),
                    overlay_width,
                    overlay_height,
                    notify_moved=False,
                )
                return

            x, y = self._default_overlay_position(overlay_width, overlay_height)
            self._set_overlay_geometry(
                overlay_window,
                x,
                y,
                overlay_width,
                overlay_height,
                notify_moved=False,
            )
        except Exception:
            logger.debug("オーバーレイジオメトリの同期に失敗", exc_info=True)
            return

    @staticmethod
    def _set_overlay_geometry(
        overlay_window: QWidget,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        notify_moved: bool,
    ) -> None:
        set_overlay_geometry = getattr(
            type(overlay_window),
            "set_overlay_geometry",
            None,
        )
        if callable(set_overlay_geometry):
            cast(Any, overlay_window).set_overlay_geometry(
                int(x),
                int(y),
                int(width),
                int(height),
                notify_moved=notify_moved,
            )
            return
        overlay_window.setGeometry(int(x), int(y), int(width), int(height))

    def _evaluate_overlay_visibility(self) -> Tuple[bool, str]:
        """オーバーレイ表示可否と理由を返す."""
        if bool(self.is_main_window_visible()):
            if not self.has_playing_games():
                return False, "no_playing_game"
            if self._is_own_window_foreground():
                return False, "own_window_foreground"
            if self.today_display_cover_state is not None:
                try:
                    covered, reason = self.today_display_cover_state()
                    return (True, reason) if covered else (False, reason)
                except Exception:
                    logger.debug("今日のプレイ時間被覆判定に失敗", exc_info=True)
            elif bool(self.is_main_window_active()):
                return False, "main_window_foreground"
            return True, "main_window_background"

        if not bool(self.get_tray_overlay_enabled()):
            return False, "tray_overlay_disabled"
        if not self.has_playing_games():
            return False, "no_playing_game"
        return True, "tray_overlay_enabled"

    def _is_own_window_foreground(self) -> bool:
        """Return whether the foreground window belongs to this app."""
        if bool(self.is_main_window_active()):
            return True

        try:
            active_window = QApplication.activeWindow()
            if self.is_active_window_own(active_window):
                return True
        except Exception:
            logger.debug("Qt active window 判定に失敗", exc_info=True)

        try:
            foreground_hwnd = get_foreground_hwnd()
            if foreground_hwnd and self.is_own_window is not None:
                return bool(self.is_own_window(foreground_hwnd))
        except Exception:
            logger.debug("前面ウィンドウ判定に失敗", exc_info=True)

        return False

    def should_show_overlay(self) -> bool:
        """Return whether the tray overlay should be visible."""
        should_show, _ = self._evaluate_overlay_visibility()
        return should_show

    def _log_overlay_visibility(self, should_show: bool, reason: str) -> None:
        """判定理由を状態変化時または定期的にINFO出力する。"""
        now = time.monotonic()
        state = self.visibility_log_state
        state_changed = (
            state.last_should_show != should_show
            or state.last_reason != reason
        )
        should_log = state_changed or (now - state.last_log_monotonic >= 5.0)
        if not should_log:
            return

        logger.info(
            "overlay visibility: %s (%s)",
            "show" if should_show else "hide",
            reason,
        )
        state.last_should_show = should_show
        state.last_reason = reason
        state.last_log_monotonic = now

    def sync_overlay_visibility(self) -> None:
        """表示条件に応じてオーバーレイを表示/非表示する."""
        overlay_window = self.overlay_window_provider()
        if overlay_window is None:
            return

        self._hide_visible_overlay_before_cover_check(overlay_window)
        should_show, reason = self._evaluate_overlay_visibility()
        self._log_overlay_visibility(should_show, reason)

        was_visible = bool(getattr(overlay_window, "isVisible", lambda: False)())
        if should_show:
            if not was_visible:
                overlay_window.show()
        else:
            overlay_window.hide()

    def _hide_visible_overlay_before_cover_check(self, overlay_window: QWidget) -> None:
        """Avoid treating the overlay itself as a cover while the main window is visible."""
        if not bool(self.is_main_window_visible()):
            return
        if not bool(getattr(overlay_window, "isVisible", lambda: False)()):
            return

        overlay_window.hide()
        try:
            QApplication.processEvents()
        except Exception:
            logger.debug("オーバーレイ非表示後のイベント処理に失敗", exc_info=True)

    def sync_overlay(self) -> None:
        """オーバーレイの表示内容・位置・可視状態を同期する."""
        self.refresh_overlay_time()
        overlay_window = self.overlay_window_provider()
        continue_drag = getattr(overlay_window, "continue_drag_from_global_cursor", None)
        is_dragging = bool(continue_drag()) if callable(continue_drag) else False
        if not is_dragging:
            self.sync_overlay_geometry()
        self.sync_overlay_visibility()

    @staticmethod
    def _clamp_overlay_position(x: int, y: int, width: int, height: int) -> Tuple[int, int]:
        try:
            screen_at = getattr(QApplication, "screenAt", None)
            cursor_pos = QCursor.pos()
            screen = screen_at(cursor_pos) if callable(screen_at) else None
            if screen is None:
                primary_screen = getattr(QApplication, "primaryScreen", None)
                screen = primary_screen() if callable(primary_screen) else None
            if screen is None:
                return x, y
            available = screen.availableGeometry()
            left = int(available.x())
            top = int(available.y())
            right = int(available.x() + available.width())
            bottom = int(available.y() + available.height())
            max_x = max(left, right - width)
            max_y = max(top, bottom - height)
            return min(max(x, left), max_x), min(max(y, top), max_y)
        except Exception:
            return x, y

    @staticmethod
    def _default_overlay_position(width: int, height: int) -> Tuple[int, int]:
        try:
            screen_at = getattr(QApplication, "screenAt", None)
            cursor_pos = QCursor.pos()
            screen = screen_at(cursor_pos) if callable(screen_at) else None
            primary_screen = getattr(QApplication, "primaryScreen", None)
            if screen is None:
                screen = primary_screen() if callable(primary_screen) else None
            if screen is None:
                return OVERLAY_DEFAULT_MARGIN, OVERLAY_DEFAULT_MARGIN
            available = screen.availableGeometry()
            left = int(available.x())
            top = int(available.y())
            right = int(available.x() + available.width())
            x = max(left, right - int(width) - OVERLAY_DEFAULT_MARGIN)
            y = top + OVERLAY_DEFAULT_MARGIN
            return x, y
        except Exception:
            return OVERLAY_DEFAULT_MARGIN, OVERLAY_DEFAULT_MARGIN

    @staticmethod
    def _overlay_rect(overlay_window: QWidget) -> Optional[Tuple[int, int, int, int]]:
        try:
            geometry = overlay_window.geometry()
            left = int(geometry.x())
            top = int(geometry.y())
            width = int(geometry.width())
            height = int(geometry.height())
            return left, top, left + width, top + height
        except Exception:
            return None

    def close_overlay(self) -> None:
        """オーバーレイを閉じて参照を解放する."""
        overlay_window = self.overlay_window_provider()
        if overlay_window is None:
            return
        overlay_window.close()
        self.set_overlay_window(None)


__all__ = [
    "MainWindowOverlayController",
    "TodayTimeOverlayWindow",
    "MK_LBUTTON",
    "QCursor",
    "WM_LBUTTONDOWN",
    "WM_LBUTTONUP",
    "WM_MOUSEMOVE",
    "_WinMsg",
    "sys",
]
