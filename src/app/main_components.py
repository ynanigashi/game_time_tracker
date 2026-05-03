"""MainWindow の補助コンポーネント群。"""

import ctypes
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypeVar,
    cast,
)

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QWidget,
)

from src.core.models import GameEntry
from src.core.services import (
    DailyStatsTracker,
    GameInfoLoader,
    GameStateTracker,
    Messages,
    MIN_PLAY_MINUTES,
    ScanResult,
    SessionRecorder,
    WindowScanner,
)
from src.core.time_utils import (
    SECONDS_PER_MINUTE,
    calc_today_elapsed_seconds,
    format_hms,
)
from src.core.window_state import DISPLAY_MODES, MODE_DEFAULT_SIZES, WindowState
from src.infra.config_loader import ConfigLoader, ConfigNotConfiguredError
from src.infra.log_handler import LogHandler
from src.infra.settings_store import SettingsStore
from src.ui.gui_layout import LayoutWidgets

logger = logging.getLogger(__name__)

OVERLAY_FALLBACK_WIDTH = 240
OVERLAY_FALLBACK_HEIGHT = 40
OVERLAY_DEFAULT_MARGIN = 24
OVERLAY_DRAG_HANDLE_WIDTH = 8
WM_NCHITTEST = 0x0084
WM_SETCURSOR = 0x0020
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_EXITSIZEMOVE = 0x0232
MK_LBUTTON = 0x0001
HTTRANSPARENT = -1
HTCLIENT = 1
MIN_MODE_SAFE_WIDTH = 320
MIN_MODE_SAFE_HEIGHT = 110
_USER32 = ctypes.windll.user32 if sys.platform == "win32" else None


class _GeometryLike(Protocol):
    """QRect 互換の最小インターフェース."""

    def width(self) -> int: ...
    def height(self) -> int: ...
    def x(self) -> int: ...
    def y(self) -> int: ...


class _WinRect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


if _USER32 is not None:
    _USER32.GetWindowRect.restype = ctypes.c_int
    _USER32.SetCapture.restype = ctypes.c_void_p
    _USER32.ReleaseCapture.restype = ctypes.c_int
    _USER32.GetAsyncKeyState.restype = ctypes.c_short


def clamp_mode_size(display_mode: str, width: int, height: int) -> Tuple[int, int]:
    """表示モードごとの最低サイズを保証する。"""
    if display_mode == "min":
        return max(width, MIN_MODE_SAFE_WIDTH), max(height, MIN_MODE_SAFE_HEIGHT)
    return width, height


class _OverlayDragHandle(QLabel):
    """Small handle that moves the parent overlay while dragged."""

    def __init__(self, overlay: "TodayTimeOverlayWindow") -> None:
        super().__init__("", overlay)
        self._overlay = overlay

    def mousePressEvent(self, event: object) -> None:
        if self._overlay.start_handle_drag(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: object) -> None:
        if self._overlay.move_handle_drag(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:
        if self._overlay.finish_handle_drag(event):
            return
        super().mouseReleaseEvent(event)


class OverlayDragHandleWindow(QWidget):
    """Separate top-level drag handle for the click-through overlay."""

    def __init__(self, overlay: "TodayTimeOverlayWindow") -> None:
        super().__init__()
        self._overlay = overlay
        self._configure_window()
        self.resize(OVERLAY_DRAG_HANDLE_WIDTH, OVERLAY_FALLBACK_HEIGHT)

    def _configure_window(self) -> None:
        flags = (
            TodayTimeOverlayWindow._window_flag("Tool")
            | TodayTimeOverlayWindow._window_flag("FramelessWindowHint")
            | TodayTimeOverlayWindow._window_flag("WindowStaysOnTopHint")
        )
        self.setWindowFlags(flags)
        self.setWindowOpacity(0.88)
        self.setStyleSheet(
            "QWidget {"
            "  background-color: rgba(255, 255, 255, 90);"
            "  border-top-left-radius: 8px;"
            "  border-bottom-left-radius: 8px;"
            "}"
        )
        attribute = TodayTimeOverlayWindow._widget_attribute("WA_ShowWithoutActivating")
        if attribute is not None:
            self.setAttribute(cast(Any, attribute), True)
        cursor_shape = TodayTimeOverlayWindow._drag_cursor_shape(active=False)
        if cursor_shape is not None:
            self.setCursor(cursor_shape)

    def sync_to_overlay(self) -> None:
        try:
            geometry = self._overlay.geometry()
            self.setGeometry(
                int(geometry.x()),
                int(geometry.y()),
                OVERLAY_DRAG_HANDLE_WIDTH,
                max(1, int(geometry.height())),
            )
        except Exception:
            logger.debug("オーバーレイハンドル位置の同期に失敗", exc_info=True)

    def mousePressEvent(self, event: object) -> None:
        if self._overlay.start_handle_drag(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: object) -> None:
        if self._overlay.move_handle_drag(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:
        if self._overlay.finish_handle_drag(event):
            return
        super().mouseReleaseEvent(event)


class TodayTimeOverlayWindow(QWidget):
    """フルスクリーンゲーム中に表示する、今日の時間専用オーバーレイ."""

    def __init__(
        self,
        *,
        on_moved: Optional[Callable[[int, int], None]] = None,
        on_dragged: Optional[Callable[[int, int], None]] = None,
        on_move_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self._on_moved = on_moved
        self._on_dragged = on_dragged
        self._on_move_finished = on_move_finished
        self._drag_offset: Optional[Tuple[int, int]] = None
        self._suppress_moved_callback = False
        self._drag_handle = _OverlayDragHandle(self)
        self._time_display = QLabel("00:00:00.0", self)
        self._drag_handle_window = OverlayDragHandleWindow(self)
        self._configure_window()
        self._build_layout()
        self.resize(OVERLAY_FALLBACK_WIDTH, OVERLAY_FALLBACK_HEIGHT)

    @staticmethod
    def _window_flag(flag_name: str) -> Any:
        window_type = getattr(Qt, "WindowType", None)
        if window_type is not None and hasattr(window_type, flag_name):
            return getattr(window_type, flag_name)
        return getattr(Qt, flag_name, 0)

    @staticmethod
    def _widget_attribute(attribute_name: str) -> Optional[object]:
        widget_attribute = getattr(Qt, "WidgetAttribute", None)
        if widget_attribute is not None and hasattr(widget_attribute, attribute_name):
            return getattr(widget_attribute, attribute_name)
        return getattr(Qt, attribute_name, None)

    def _set_widget_attribute(self, attribute_name: str, enabled: bool = True) -> None:
        attribute = self._widget_attribute(attribute_name)
        if attribute is not None:
            self.setAttribute(cast(Any, attribute), enabled)

    def _configure_window(self) -> None:
        flags = (
            self._window_flag("Tool")
            | self._window_flag("FramelessWindowHint")
            | self._window_flag("WindowStaysOnTopHint")
            | self._window_flag("WindowTransparentForInput")
        )
        self.setWindowFlags(flags)
        self.setWindowOpacity(0.88)

        self._set_widget_attribute("WA_TranslucentBackground")
        self._set_widget_attribute("WA_ShowWithoutActivating")
        self._set_widget_attribute("WA_TransparentForMouseEvents")

        focus_policy_enum = getattr(Qt, "FocusPolicy", None)
        no_focus_policy = (
            getattr(focus_policy_enum, "NoFocus", None)
            if focus_policy_enum is not None
            else None
        )
        if no_focus_policy is not None:
            self.setFocusPolicy(no_focus_policy)

    def _build_layout(self) -> None:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._drag_handle.setFixedWidth(OVERLAY_DRAG_HANDLE_WIDTH)
        self._drag_handle.setStyleSheet(
            "QLabel {"
            "  background-color: rgba(255, 255, 255, 90);"
            "  border-top-left-radius: 8px;"
            "  border-bottom-left-radius: 8px;"
            "}"
        )
        self._set_drag_cursor(active=False)

        self._time_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_display.setStyleSheet(
            "QLabel {"
            "  background-color: rgba(15, 15, 15, 190);"
            "  color: #FFFFFF;"
            "  border-top-right-radius: 8px;"
            "  border-bottom-right-radius: 8px;"
            "  font-size: 20px;"
            "  font-weight: bold;"
            "  padding: 2px 6px;"
            "}"
        )
        layout.addWidget(self._drag_handle)
        layout.addWidget(self._time_display)
        self.setLayout(layout)

    def set_today_text(self, formatted_time: str) -> None:
        self._time_display.setText(formatted_time)

    def set_overlay_geometry(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        notify_moved: bool = True,
    ) -> None:
        previous = self._suppress_moved_callback
        self._suppress_moved_callback = not bool(notify_moved)
        try:
            self.setGeometry(int(x), int(y), int(width), int(height))
        finally:
            self._suppress_moved_callback = previous

    def moveEvent(self, event: object) -> None:
        super().moveEvent(event)
        self._sync_drag_handle_window()
        self._notify_moved()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._sync_drag_handle_window()

    def show(self) -> None:
        super().show()
        self._sync_drag_handle_window()
        self._drag_handle_window.show()

    def hide(self) -> None:
        self._drag_handle_window.hide()
        super().hide()

    def close(self) -> bool:
        self._drag_handle_window.close()
        return bool(super().close())

    def _sync_drag_handle_window(self) -> None:
        handle = getattr(self, "_drag_handle_window", None)
        if handle is not None:
            handle.sync_to_overlay()

    def nativeEvent(self, event_type: object, message: object) -> Tuple[bool, int]:
        native_result = self._handle_native_overlay_event(message)
        if native_result is not None:
            return True, native_result
        return cast(Tuple[bool, int], super().nativeEvent(event_type, message))

    def _handle_native_overlay_event(self, message: object) -> Optional[int]:
        if sys.platform != "win32":
            return None
        try:
            msg = _WinMsg.from_address(int(message))
        except Exception:
            return None

        message_id = int(msg.message)
        if message_id == WM_SETCURSOR:
            point = self._cursor_global_point()
            if point is not None:
                self._set_drag_cursor(
                    active=self._drag_offset is not None,
                    over_handle=self._is_drag_handle_global_point(*point),
                )
            return None
        if message_id == WM_NCHITTEST:
            return self._native_hit_test_result(int(msg.lParam))
        if message_id == WM_LBUTTONDOWN:
            point = self._cursor_global_point()
            if point is not None and self._is_drag_handle_global_point(*point):
                self._start_drag_at_global_point(*point)
                self._capture_mouse()
                return 0
        if message_id == WM_MOUSEMOVE and self._drag_offset is not None:
            if int(msg.wParam) & MK_LBUTTON:
                point = self._cursor_global_point()
                if point is not None:
                    self._move_drag_to_global_point(*point)
                return 0
            self._finish_drag()
            return 0
        if message_id == WM_LBUTTONUP and self._drag_offset is not None:
            self._finish_drag()
            return 0
        if message_id == WM_EXITSIZEMOVE:
            if self._on_move_finished is not None:
                self._on_move_finished()
            return None
        return None

    def _native_hit_test_result(self, lparam: int) -> int:
        x = self._signed_word(int(lparam))
        y = self._signed_word(int(lparam) >> 16)
        over_handle = self._is_drag_handle_global_point(x, y)
        self._set_drag_cursor(active=self._drag_offset is not None, over_handle=over_handle)
        if over_handle:
            return HTCLIENT
        return HTTRANSPARENT

    @staticmethod
    def _signed_word(value: int) -> int:
        value &= 0xFFFF
        return value - 0x10000 if value & 0x8000 else value

    def _is_drag_handle_global_point(self, x: int, y: int) -> bool:
        rect = self._native_window_rect()
        if rect is not None:
            left, top, right, bottom = rect
            handle_width = self._native_drag_handle_width(right - left)
            return left <= int(x) < left + handle_width and top <= int(y) < bottom

        try:
            geometry = self.geometry()
            left = int(geometry.x())
            top = int(geometry.y())
            height = int(geometry.height())
        except Exception:
            return False
        return (
            left <= int(x) < left + OVERLAY_DRAG_HANDLE_WIDTH
            and top <= int(y) < top + height
        )

    def _native_window_rect(self) -> Optional[Tuple[int, int, int, int]]:
        if _USER32 is None:
            return None
        try:
            hwnd = int(self.winId())
        except Exception:
            return None
        rect = _WinRect()
        try:
            if _USER32.GetWindowRect(hwnd, ctypes.byref(rect)) == 0:
                return None
        except Exception:
            return None
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)

    def _native_drag_handle_width(self, native_window_width: int) -> int:
        try:
            logical_width = max(1, int(self.width()))
            scale = max(1.0, float(native_window_width) / float(logical_width))
        except Exception:
            scale = 1.0
        return max(1, int(round(OVERLAY_DRAG_HANDLE_WIDTH * scale)))

    def start_handle_drag(self, event: object) -> bool:
        if not self._is_left_button_event(event):
            return False
        point = self._global_point_from_event(event)
        if point is None:
            return False
        self._start_drag_at_global_point(*point)
        self._accept_event(event)
        return True

    def move_handle_drag(self, event: object) -> bool:
        if self._drag_offset is None:
            return False
        if not self._has_left_button(event):
            self.finish_handle_drag(event)
            return True
        point = self._global_point_from_event(event)
        if point is None:
            return False

        self._move_drag_to_global_point(*point)
        self._accept_event(event)
        return True

    def finish_handle_drag(self, event: object) -> bool:
        if self._drag_offset is None:
            return False
        self._finish_drag()
        self._accept_event(event)
        return True

    def is_dragging(self) -> bool:
        return self._drag_offset is not None

    def continue_drag_from_global_cursor(self) -> bool:
        if self._drag_offset is None:
            return False
        if not self._is_left_mouse_button_pressed():
            self._finish_drag()
            return False
        point = self._cursor_global_point()
        if point is None:
            return True
        self._move_drag_to_global_point(*point)
        return True

    def _start_drag_at_global_point(self, x: int, y: int) -> None:
        try:
            geometry = self.geometry()
            self._drag_offset = (
                int(x) - int(geometry.x()),
                int(y) - int(geometry.y()),
            )
            self._set_drag_cursor(active=True, over_handle=True)
        except Exception:
            self._drag_offset = None

    def _move_drag_to_global_point(self, x: int, y: int) -> None:
        if self._drag_offset is None:
            return
        offset_x, offset_y = self._drag_offset
        self.move(int(x) - offset_x, int(y) - offset_y)
        self._notify_moved()

    def _finish_drag(self) -> None:
        final_position = self._current_position()
        self._drag_offset = None
        self._release_mouse()
        self._set_drag_cursor(active=False, over_handle=False)
        if self._on_dragged is not None and final_position is not None:
            try:
                self._on_dragged(*final_position)
            except Exception:
                logger.debug("オーバーレイドラッグ終了位置の通知に失敗", exc_info=True)
        if self._on_move_finished is not None:
            self._on_move_finished()

    def _current_position(self) -> Optional[Tuple[int, int]]:
        try:
            geometry = self.geometry()
            return int(geometry.x()), int(geometry.y())
        except Exception:
            return None

    def _capture_mouse(self) -> None:
        if _USER32 is None:
            return
        try:
            _USER32.SetCapture(int(self.winId()))
        except Exception:
            logger.debug("オーバーレイのマウスキャプチャに失敗", exc_info=True)

    @staticmethod
    def _release_mouse() -> None:
        if _USER32 is None:
            return
        try:
            _USER32.ReleaseCapture()
        except Exception:
            logger.debug("オーバーレイのマウスキャプチャ解除に失敗", exc_info=True)

    @staticmethod
    def _cursor_global_point() -> Optional[Tuple[int, int]]:
        try:
            point = QCursor.pos()
            return int(point.x()), int(point.y())
        except Exception:
            return None

    @staticmethod
    def _is_left_mouse_button_pressed() -> bool:
        if _USER32 is not None:
            try:
                return bool(_USER32.GetAsyncKeyState(0x01) & 0x8000)
            except Exception:
                logger.debug("左マウスボタン状態の取得に失敗", exc_info=True)
        try:
            buttons = QApplication.mouseButtons()
            return bool(buttons & Qt.MouseButton.LeftButton)
        except Exception:
            return False

    def _set_drag_cursor(self, *, active: bool, over_handle: bool = True) -> None:
        if not active and not over_handle:
            self._unset_overlay_cursor()
            self._set_handle_cursor(active=False)
            return

        cursor_shape = self._drag_cursor_shape(active=active)
        if cursor_shape is not None:
            self.setCursor(cursor_shape)
            self._drag_handle.setCursor(cursor_shape)
            self._drag_handle_window.setCursor(cursor_shape)

    def _set_handle_cursor(self, *, active: bool) -> None:
        cursor_shape = self._drag_cursor_shape(active=active)
        if cursor_shape is not None:
            self._drag_handle.setCursor(cursor_shape)
            self._drag_handle_window.setCursor(cursor_shape)

    @staticmethod
    def _drag_cursor_shape(*, active: bool) -> Optional[object]:
        cursor_enum = getattr(Qt, "CursorShape", None)
        cursor_name = "ClosedHandCursor" if active else "OpenHandCursor"
        cursor_shape = (
            getattr(cursor_enum, cursor_name, None)
            if cursor_enum is not None
            else None
        )
        if cursor_shape is None:
            cursor_shape = getattr(Qt, cursor_name, None)
        if cursor_shape is None:
            cursor_shape = getattr(
                cursor_enum,
                "SizeAllCursor",
                getattr(Qt, "SizeAllCursor", None),
            )
        return cursor_shape

    def _unset_overlay_cursor(self) -> None:
        unset_cursor = getattr(self, "unsetCursor", None)
        if callable(unset_cursor):
            unset_cursor()

    def _notify_moved(self) -> None:
        if self._suppress_moved_callback:
            return
        if self._on_moved is None:
            return
        try:
            geometry = self.geometry()
            self._on_moved(int(geometry.x()), int(geometry.y()))
        except Exception:
            logger.debug("オーバーレイ位置の更新に失敗", exc_info=True)

    @staticmethod
    def _global_point_from_event(event: object) -> Optional[Tuple[int, int]]:
        for attr_name in ("globalPosition", "globalPos"):
            point_getter = getattr(event, attr_name, None)
            if not callable(point_getter):
                continue
            try:
                point = point_getter()
                return int(point.x()), int(point.y())
            except Exception:
                continue
        return None

    @staticmethod
    def _is_left_button_event(event: object) -> bool:
        button_getter = getattr(event, "button", None)
        if not callable(button_getter):
            return False
        try:
            return button_getter() == Qt.MouseButton.LeftButton
        except Exception:
            return False

    @staticmethod
    def _has_left_button(event: object) -> bool:
        buttons_getter = getattr(event, "buttons", None)
        if not callable(buttons_getter):
            return True
        try:
            return bool(buttons_getter() & Qt.MouseButton.LeftButton)
        except Exception:
            return True

    @staticmethod
    def _accept_event(event: object) -> None:
        accept = getattr(event, "accept", None)
        if callable(accept):
            accept()


class _WinPoint(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class _WinMsg(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_size_t),
        ("time", ctypes.c_uint),
        ("pt", _WinPoint),
    ]


class MainWindowUiController:
    """MainWindow の UI 更新専用ロジック."""

    def __init__(self, widgets: LayoutWidgets, daily_stats: DailyStatsTracker) -> None:
        self.w = widgets
        self.daily_stats = daily_stats

    @staticmethod
    def all_playing_games(
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> List[GameEntry]:
        """アクティブ/非アクティブを統合したプレイ中ゲーム一覧を返す."""
        return list(active_games) + list(inactive_games)

    def update_active_list(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> None:
        """プレイ中ゲームリストを更新."""
        if not active_games and not inactive_games:
            self.w.active_display.setText('---')
            return

        parts = [game.game_title for game in active_games]
        parts.extend(f'{game.game_title} - 停止中' for game in inactive_games)
        self.w.active_display.setText(' / '.join(parts))

    def update_session_times(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> None:
        """現在のセッション時間を更新（最長セッションを表示）。"""
        all_playing = self.all_playing_games(active_games, inactive_games)
        if not all_playing:
            self.w.session_time_display.setText('---')
            return

        max_elapsed = max(
            (now - game.start_time).total_seconds()
            if game.start_time else 0
            for game in all_playing
        )
        self.w.session_time_display.setText(format_hms(max_elapsed))

    def calculate_today_total_seconds(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> float:
        """今日のプレイ時間（完了+進行中）秒数を計算する。"""
        total_seconds = self.daily_stats.today_completed_seconds
        min_seconds = MIN_PLAY_MINUTES * SECONDS_PER_MINUTE

        all_playing = self.all_playing_games(active_games, inactive_games)
        for game in all_playing:
            if game.start_time:
                elapsed_seconds = calc_today_elapsed_seconds(game.start_time, now)
                if elapsed_seconds >= min_seconds:
                    total_seconds += elapsed_seconds
        return total_seconds

    def update_today_totals(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> float:
        """今日のプレイ時間（完了+進行中）を更新."""
        total_seconds = self.calculate_today_total_seconds(
            active_games, inactive_games, now)
        self.w.today_time_display.setText(format_hms(total_seconds))
        return total_seconds

    def update_window_list(self, window_titles: Sequence[str]) -> None:
        """現在のウィンドウタイトルリストを更新."""
        self.w.window_list.clear()
        for title in window_titles:
            self.w.window_list.addItem(title)

    def update_today_games_list(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> None:
        """今日プレイしたゲームの一覧と時間を更新."""
        game_minutes = dict(self.daily_stats.today_game_minutes_cache)
        all_playing = self.all_playing_games(active_games, inactive_games)

        if not game_minutes and not all_playing:
            if self.daily_stats.last_today_games_content != "":
                self.daily_stats.last_today_games_content = ""
                self.w.today_games_table.setRowCount(0)
            return

        for game in all_playing:
            current_minutes = (
                calc_today_elapsed_seconds(game.start_time, now) / SECONDS_PER_MINUTE
                if game.start_time else 0.0
            )
            if current_minutes >= MIN_PLAY_MINUTES:
                game_minutes[game.game_title] = game_minutes.get(
                    game.game_title, 0) + current_minutes

        sorted_games = sorted(game_minutes.items(), key=lambda x: x[1], reverse=True)
        content = '\n'.join(
            f'{game_title}: {int(minutes)}分' for game_title, minutes in sorted_games)

        if content != self.daily_stats.last_today_games_content:
            self.daily_stats.last_today_games_content = content
            self.w.today_games_table.setRowCount(len(sorted_games))
            for row, (game_title, minutes) in enumerate(sorted_games):
                self.w.today_games_table.setItem(row, 0, QTableWidgetItem(game_title))
                self.w.today_games_table.setItem(
                    row, 1, QTableWidgetItem(f'{int(minutes)}分'))


class MainWindowDisplayController:
    """MainWindow の表示モード制御ロジック."""

    def __init__(self, max_widget_height: int) -> None:
        self.max_widget_height = max_widget_height

    def set_widget_visibility(self, widget: QWidget, visible: bool) -> None:
        """ウィジェットの表示/非表示を設定."""
        widget.setVisible(visible)

    def set_widget_with_height(
        self,
        widget: QWidget,
        visible: bool,
        *,
        min_height: int,
        max_height: int,
    ) -> None:
        """ウィジェットの表示/非表示と高さ制約を設定."""
        widget.setVisible(visible)
        widget.setMinimumHeight(min_height)
        widget.setMaximumHeight(max_height)

    def apply_mode_geometry(
        self,
        window: QWidget,
        display_mode: str,
        mode_sizes: Dict[str, Tuple[int, int]],
    ) -> None:
        """表示モードに応じたサイズを適用."""
        w, h = mode_sizes.get(display_mode, MODE_DEFAULT_SIZES[display_mode])
        w, h = clamp_mode_size(display_mode, int(w), int(h))
        mode_sizes[display_mode] = (w, h)
        # サイズを強制適用するため、一時的に min/max を固定
        window.setMinimumHeight(h)
        window.setMaximumHeight(h)
        window.resize(w, h)
        window.setMinimumHeight(0)
        window.setMaximumHeight(self.max_widget_height)

    def apply_display_mode(
        self,
        *,
        display_mode: str,
        widgets: LayoutWidgets,
        set_widget_visibility: Callable[[QWidget, bool], None],
        set_widget_with_height: Callable[..., None],
        apply_mode_geometry: Callable[[], None],
    ) -> None:
        """表示モードに応じてウィジェット表示を切り替え."""
        is_expanded = display_mode != "min"  # mid/maxで表示
        is_max = display_mode == "max"

        # minではラベルを隠して時間表示領域を優先
        set_widget_visibility(widgets.today_label, is_expanded)
        set_widget_visibility(widgets.today_time_display, True)

        # mid/maxで表示
        set_widget_visibility(widgets.session_label, is_expanded)
        set_widget_with_height(
            widgets.session_time_display,
            is_expanded,
            min_height=0,
            max_height=self.max_widget_height if is_expanded else 0,
        )

        set_widget_visibility(widgets.active_label, is_expanded)
        set_widget_with_height(
            widgets.active_display,
            is_expanded,
            min_height=widgets.active_min_height if is_expanded else 0,
            max_height=widgets.active_max_height if is_expanded else 0,
        )

        set_widget_visibility(widgets.today_games_label, is_expanded)
        set_widget_with_height(
            widgets.today_games_table,
            is_expanded,
            min_height=widgets.today_games_min_height if is_expanded else 0,
            max_height=self.max_widget_height if is_expanded else 0,
        )

        # maxのみ表示
        set_widget_visibility(widgets.window_label, is_max)
        set_widget_with_height(
            widgets.window_list,
            is_max,
            min_height=0,
            max_height=self.max_widget_height if is_max else 0,
        )

        if widgets.overtime_alert_toggle is not None:
            set_widget_visibility(widgets.overtime_alert_toggle, True)
        if widgets.report_button is not None:
            set_widget_visibility(widgets.report_button, True)
        if getattr(widgets, "manual_record_button", None) is not None:
            set_widget_visibility(widgets.manual_record_button, True)

        apply_mode_geometry()

    def next_display_mode(self, current_display_mode: str) -> str:
        """現在の表示モードから次のモードを返す."""
        idx = DISPLAY_MODES.index(current_display_mode)
        return DISPLAY_MODES[(idx + 1) % len(DISPLAY_MODES)]


class MainWindowStateController:
    """MainWindow の状態読み書きロジック."""

    def __init__(
        self,
        state_file: Path,
        settings_store: Optional[SettingsStore] = None,
    ) -> None:
        self.state_file = state_file
        self.settings_store = settings_store or SettingsStore()
        self.settings_store.migrate_window_state_file(self.state_file)

    def load_all(self) -> Tuple[int, int, str, Dict[str, Tuple[int, int]], bool]:
        """永続化されたウィンドウ状態と設定を読み込む."""
        data = self.settings_store.load_window_state()
        if data is None:
            return WindowState.load_all(self.state_file)
        return WindowState.load_all_from_data(data)

    def load(self) -> Tuple[int, int, str, Dict[str, Tuple[int, int]]]:
        """永続化されたウィンドウ状態を読み込む."""
        x, y, mode, mode_sizes, _ = self.load_all()
        return x, y, mode, mode_sizes

    def load_overtime_alert_enabled(self) -> bool:
        """時間超過防止アラート設定を読み込む."""
        _, _, _, _, overtime_alert_enabled = self.load_all()
        return overtime_alert_enabled

    def _load_raw_state(self) -> Dict[str, object]:
        data = self.settings_store.load_window_state()
        if data is None:
            return WindowState._load_data(self.state_file)
        return data

    def load_startup_window_visible(self) -> bool:
        return WindowState.load_startup_window_visible_from_data(self._load_raw_state())

    def load_tray_overlay_enabled(self) -> bool:
        return WindowState.load_tray_overlay_enabled_from_data(self._load_raw_state())

    def load_overlay_position(self) -> Optional[Tuple[int, int]]:
        return WindowState.load_overlay_position_from_data(self._load_raw_state())

    def save(
        self,
        geom: _GeometryLike,
        display_mode: str,
        mode_sizes: Dict[str, Tuple[int, int]],
        overtime_alert_enabled: bool,
        startup_window_visible: bool = False,
        tray_overlay_enabled: bool = False,
        overlay_position: Optional[Tuple[int, int]] = None,
    ) -> None:
        """現在状態を mode_sizes に反映して永続化."""
        mode_sizes[display_mode] = clamp_mode_size(
            display_mode,
            int(geom.width()),
            int(geom.height()),
        )
        data = WindowState.to_data(
            geom.x(),
            geom.y(),
            display_mode,
            mode_sizes,
            overtime_alert_enabled=bool(overtime_alert_enabled),
            startup_window_visible=bool(startup_window_visible),
            tray_overlay_enabled=bool(tray_overlay_enabled),
            overlay_position=overlay_position,
        )
        self.settings_store.save_window_state(data)

    @staticmethod
    def record_resize(
        mode_sizes: Dict[str, Tuple[int, int]],
        display_mode: str,
        width: int,
        height: int,
    ) -> None:
        """リサイズ後サイズを mode_sizes に反映."""
        mode_sizes[display_mode] = clamp_mode_size(
            display_mode,
            int(width),
            int(height),
        )


class MainWindowLoopController:
    """MainWindow のタイマー起動と tick オーケストレーション."""

    def __init__(self, timer_factory: Callable[[QWidget], QTimer] = QTimer) -> None:
        self._timer_factory = timer_factory

    def start_timer(
        self,
        owner: QWidget,
        interval_seconds: float,
        callback: Callable[[], None],
    ) -> QTimer:
        """タイマーを作成して開始."""
        timer = self._timer_factory(owner)
        timer.setInterval(int(interval_seconds * 1000))
        timer.timeout.connect(callback)
        timer.start()
        return timer

    def run_scan_tick(self, window: "MainWindow") -> None:
        """監視サイクル（1秒間隔）."""
        if not window.games:
            return

        if window.daily_stats.check_day_change():
            # 日付変更時、UIも強制クリア
            window.w.today_games_table.setRowCount(0)
            window._prime_overtime_alert_progress(0.0)

        window_titles = window.scanner.get_titles()
        foreground_title = window.scanner.get_foreground_title()
        result = window._scan_games(window_titles, foreground_title)
        window._apply_scan_result(window_titles, result)

    def run_ui_tick(self, window: "MainWindow") -> None:
        """UIだけを高速更新（0.1秒間隔）."""
        now = datetime.now()
        # セッション時間と今日の合計時間のみ更新（リストはスキャン時に更新）
        window._update_session_times(window.active_games_cache, now)
        total_seconds = window._update_today_totals(window.active_games_cache, now)
        window._update_today_games_list(now)
        window._update_overtime_alert(total_seconds)


class MainWindowOverlayController:
    """MainWindow のオーバーレイ表示制御ロジック."""

    def __init__(self, owner: "MainWindow") -> None:
        self.owner = owner
        self._last_overlay_should_show: Optional[bool] = None
        self._last_overlay_reason: Optional[str] = None
        self._last_overlay_log_monotonic: float = 0.0

    def initialize_overlay(self) -> None:
        """今日のプレイ時間オーバーレイを初期化する."""
        if self.owner._get_overlay_window() is not None:
            return

        try:
            self.owner.overlay_window = TodayTimeOverlayWindow(
                on_moved=self._on_overlay_moved,
                on_dragged=self._on_overlay_dragged,
                on_move_finished=self._save_overlay_position,
            )
            self.owner.overlay_window.hide()
            self.sync_overlay()
        except Exception as e:
            logger.warning("オーバーレイ初期化に失敗したため無効化します: %s", e)
            self.owner.overlay_window = None

    def _on_overlay_moved(self, x: int, y: int) -> None:
        self.owner.overlay_position = (int(x), int(y))

    def _on_overlay_dragged(self, x: int, y: int) -> None:
        if not bool(getattr(self.owner, "isVisible", lambda: False)()):
            return
        self._move_owner_today_display_to(int(x), int(y))

    def _move_owner_today_display_to(self, x: int, y: int) -> None:
        target = self.owner._get_today_time_display()
        if target is None:
            return
        try:
            top_left = target.mapToGlobal(target.rect().topLeft())
            geometry = self.owner.geometry()
            move = getattr(self.owner, "move", None)
            if not callable(move):
                return
            move(
                int(geometry.x()) + int(x) - int(top_left.x()),
                int(geometry.y()) + int(y) - int(top_left.y()),
            )
        except Exception:
            logger.debug("メインウィンドウ位置の同期に失敗", exc_info=True)

    def _save_overlay_position(self) -> None:
        save = getattr(self.owner, "_save_window_state", None)
        if callable(save):
            save()

    def refresh_overlay_time(self) -> None:
        """オーバーレイの時刻表示を更新する."""
        overlay_window = self.owner._get_overlay_window()
        today_time_display = self.owner._get_today_time_display()
        if overlay_window is None or today_time_display is None:
            return
        overlay_window.set_today_text(today_time_display.text())

    def sync_overlay_geometry(self) -> None:
        """Apply the overlay position for the current main-window state."""
        overlay_window = self.owner._get_overlay_window()
        if overlay_window is None:
            return
        is_dragging = getattr(overlay_window, "is_dragging", None)
        if callable(is_dragging) and is_dragging() is True:
            return

        try:
            if bool(getattr(self.owner, "isVisible", lambda: False)()):
                target = self.owner._get_today_time_display()
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
            manual_position = getattr(self.owner, "overlay_position", None)
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
        if bool(getattr(self.owner, "isVisible", lambda: False)()):
            if not bool(getattr(self.owner, "_has_playing_games", lambda: False)()):
                return False, "no_playing_game"
            cover_state_getter = getattr(
                self.owner,
                "_get_today_display_cover_state",
                None,
            )
            if callable(cover_state_getter):
                try:
                    covered, reason = cast(Tuple[bool, str], cover_state_getter())
                    return (True, reason) if covered else (False, reason)
                except Exception:
                    logger.debug("今日のプレイ時間被覆判定に失敗", exc_info=True)
            elif bool(getattr(self.owner, "isActiveWindow", lambda: False)()):
                return False, "main_window_foreground"
            return True, "main_window_background"

        if not bool(getattr(self.owner, "tray_overlay_enabled", False)):
            return False, "tray_overlay_disabled"
        if not bool(getattr(self.owner, "_has_playing_games", lambda: False)()):
            return False, "no_playing_game"
        return True, "tray_overlay_enabled"

    def should_show_overlay(self) -> bool:
        """Return whether the tray overlay should be visible."""
        should_show, _ = self._evaluate_overlay_visibility()
        return should_show

    def _log_overlay_visibility(self, should_show: bool, reason: str) -> None:
        """判定理由を状態変化時または定期的にINFO出力する。"""
        now = time.monotonic()
        state_changed = (
            self._last_overlay_should_show != should_show
            or self._last_overlay_reason != reason
        )
        should_log = state_changed or (now - self._last_overlay_log_monotonic >= 5.0)
        if not should_log:
            return

        logger.info(
            "overlay visibility: %s (%s)",
            "show" if should_show else "hide",
            reason,
        )
        self._last_overlay_should_show = should_show
        self._last_overlay_reason = reason
        self._last_overlay_log_monotonic = now

    def sync_overlay_visibility(self) -> None:
        """表示条件に応じてオーバーレイを表示/非表示する."""
        overlay_window = self.owner._get_overlay_window()
        if overlay_window is None:
            return

        was_visible = bool(getattr(overlay_window, "isVisible", lambda: False)())
        should_show, reason = self._evaluate_overlay_visibility()
        self._log_overlay_visibility(should_show, reason)

        if should_show:
            if not was_visible:
                overlay_window.show()
        else:
            overlay_window.hide()

    def sync_overlay(self) -> None:
        """オーバーレイの表示内容・位置・可視状態を同期する."""
        self.refresh_overlay_time()
        overlay_window = self.owner._get_overlay_window()
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
        overlay_window = self.owner._get_overlay_window()
        if overlay_window is None:
            return
        overlay_window.close()
        self.owner.overlay_window = None


class NoGamesConfiguredError(Exception):
    """ゲーム情報が1件も読み込めなかったことを示す例外."""


@dataclass
class MainWindowBootstrapResult:
    """MainWindow の初期化に必要な依存と初期データ."""

    games: List[GameEntry]
    browsers: Sequence[str]
    scanner: WindowScanner
    recorder: SessionRecorder
    state_tracker: GameStateTracker
    today_game_minutes: Dict[str, float]
    today_completed_seconds: float


class MainWindowBootstrapError(Exception):
    """MainWindow 初期化でユーザー向けに扱う例外."""

    def __init__(
        self,
        status_message: str,
        log_message: Optional[str] = None,
        *,
        open_settings: bool = False,
        open_game_catalog: bool = False,
        alert_title: Optional[str] = None,
        alert_message: Optional[str] = None,
    ) -> None:
        super().__init__(status_message)
        self.status_message = status_message
        self.log_message = log_message
        self.open_settings = open_settings
        self.open_game_catalog = open_game_catalog
        self.alert_title = alert_title
        self.alert_message = alert_message


class MainWindowBootstrapper:
    """MainWindow の依存構築・初期データ読み込みを担当."""

    def __init__(
        self,
        *,
        base_title: str,
        min_play_minutes: int,
        inactive_timeout_minutes: int,
        daily_stats: DailyStatsTracker,
        config_loader_cls: type = ConfigLoader,
        game_info_loader_cls: type = GameInfoLoader,
        window_scanner_cls: type = WindowScanner,
        log_handler_cls: type = LogHandler,
        session_recorder_cls: type = SessionRecorder,
        game_state_tracker_cls: type = GameStateTracker,
    ) -> None:
        self.base_title = base_title
        self.min_play_minutes = min_play_minutes
        self.inactive_timeout_minutes = inactive_timeout_minutes
        self.daily_stats = daily_stats
        self._config_loader_cls = config_loader_cls
        self._game_info_loader_cls = game_info_loader_cls
        self._window_scanner_cls = window_scanner_cls
        self._log_handler_cls = log_handler_cls
        self._session_recorder_cls = session_recorder_cls
        self._game_state_tracker_cls = game_state_tracker_cls

    def bootstrap(self, *, window_title: str) -> MainWindowBootstrapResult:
        """設定・サービス・初期統計をまとめて構築する."""
        try:
            config = self._config_loader_cls().load()
            games = self._game_info_loader_cls(config).load()
            if not games:
                raise NoGamesConfiguredError

            browsers = config.window_scan.browsers
            scanner = self._window_scanner_cls(
                excluded_titles=(
                    list(config.window_scan.excluded_titles)
                    + [self.base_title, window_title]
                )
            )

            log_handler = self._log_handler_cls(config.log_handler)
            recorder = self._session_recorder_cls(
                log_handler=log_handler,
                min_play_minutes=self.min_play_minutes,
            )
            state_tracker = self._game_state_tracker_cls(
                recorder=recorder,
                daily_stats=self.daily_stats,
                browsers=list(browsers),
                inactive_timeout_minutes=self.inactive_timeout_minutes,
            )
            today_game_minutes, today_completed_seconds = (
                recorder.log_handler.get_today_stats()
            )

            return MainWindowBootstrapResult(
                games=games,
                browsers=browsers,
                scanner=scanner,
                recorder=recorder,
                state_tracker=state_tracker,
                today_game_minutes=today_game_minutes,
                today_completed_seconds=today_completed_seconds,
            )
        except ConfigNotConfiguredError as e:
            raise MainWindowBootstrapError(
                "設定が未作成です。設定画面で入力して保存してください。",
                str(e),
                open_settings=True,
            ) from e
        except NoGamesConfiguredError as e:
            raise MainWindowBootstrapError(
                'ゲーム情報が未登録です。ゲーム管理で追加してください。',
                open_game_catalog=True,
            ) from e
        except FileNotFoundError as e:
            raise MainWindowBootstrapError(
                "認証情報ファイルが見つかりません。設定画面で認証JSONを確認してください。",
                f"認証情報ファイルが見つかりません: {e}",
                open_settings=True,
                alert_title="認証情報ファイルが見つかりません",
                alert_message=(
                    "設定されている認証JSONファイルを開けませんでした。\n"
                    "設定画面で認証JSONのパスを選び直してください。"
                ),
            ) from e
        except Exception as e:
            raise MainWindowBootstrapError(
                'ログハンドラー初期化エラー',
                f'ログハンドラーの初期化に失敗しました: {e}',
            ) from e
