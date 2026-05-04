"""Today-time overlay window and native drag handling."""

import ctypes
import logging
import sys
import time
from typing import (
    Any,
    Callable,
    Optional,
    Tuple,
    cast,
)

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QWidget,
)

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
_USER32 = ctypes.windll.user32 if sys.platform == "win32" else None


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


__all__ = [
    "OVERLAY_DEFAULT_MARGIN",
    "OVERLAY_DRAG_HANDLE_WIDTH",
    "OVERLAY_FALLBACK_HEIGHT",
    "OVERLAY_FALLBACK_WIDTH",
    "MK_LBUTTON",
    "QCursor",
    "TodayTimeOverlayWindow",
    "WM_LBUTTONDOWN",
    "WM_LBUTTONUP",
    "WM_MOUSEMOVE",
    "_WinMsg",
    "sys",
]
