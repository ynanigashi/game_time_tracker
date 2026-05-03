"""Win32 API ヘルパー — ウィンドウ矩形・HWND 操作を集約。"""

import ctypes
import logging
import os
import sys
from typing import Any, List, Optional, Sequence, Tuple, cast

from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

Point = Tuple[int, int]
Rect = Tuple[int, int, int, int]

_USER32 = ctypes.windll.user32 if sys.platform == "win32" else None


class _WinPoint(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class _WinRect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


if _USER32 is not None:
    _USER32.GetForegroundWindow.restype = ctypes.c_void_p
    _USER32.GetWindow.restype = ctypes.c_void_p
    _USER32.GetAncestor.restype = ctypes.c_void_p
    _USER32.WindowFromPoint.restype = ctypes.c_void_p
    _USER32.GetWindowRect.restype = ctypes.c_int
    _USER32.GetWindowThreadProcessId.restype = ctypes.c_uint
    _USER32.GetCursorPos.restype = ctypes.c_int
    _USER32.GetAsyncKeyState.restype = ctypes.c_short


# ---------------------------------------------------------------------------
# 純粋な矩形ユーティリティ
# ---------------------------------------------------------------------------

def global_rect_of_widget(widget: QWidget) -> Optional[Rect]:
    """ウィジェットのグローバル矩形を返す."""
    try:
        top_left = widget.mapToGlobal(widget.rect().topLeft())
        return (
            int(top_left.x()),
            int(top_left.y()),
            int(top_left.x() + widget.width()),
            int(top_left.y() + widget.height()),
        )
    except Exception:
        logger.debug("ウィジェットのグローバル矩形取得に失敗", exc_info=True)
        return None


def rect_contains_point(rect: Rect, x: int, y: int) -> bool:
    """矩形が点を含むか判定する."""
    return rect[0] <= x < rect[2] and rect[1] <= y < rect[3]


def rects_intersect(first_rect: Rect, second_rect: Rect) -> bool:
    """2つの矩形が交差しているか判定する."""
    left = max(first_rect[0], second_rect[0])
    top = max(first_rect[1], second_rect[1])
    right = min(first_rect[2], second_rect[2])
    bottom = min(first_rect[3], second_rect[3])
    return right > left and bottom > top


def cursor_position() -> Optional[Point]:
    """Return the current global cursor position."""
    if _USER32 is None:
        return None

    point = _WinPoint()
    if _USER32.GetCursorPos(ctypes.byref(point)) == 0:
        return None
    return int(point.x), int(point.y)


def is_right_mouse_button_pressed() -> bool:
    """Return whether the right mouse button is currently pressed globally."""
    if _USER32 is None:
        return False
    # VK_RBUTTON = 0x02; high bit means currently pressed.
    return bool(_USER32.GetAsyncKeyState(0x02) & 0x8000)


def sample_points_from_rect(
    rect: Rect,
    ratios: Sequence[Tuple[float, float]],
) -> List[Point]:
    """矩形内のサンプル点を返す."""
    left, top, right, bottom = rect
    width = max(1, right - left)
    height = max(1, bottom - top)
    points: List[Point] = []

    for x_ratio, y_ratio in ratios:
        x = left + int(width * x_ratio)
        y = top + int(height * y_ratio)
        x = min(max(x, left), right - 1)
        y = min(max(y, top), bottom - 1)
        points.append((x, y))
    return points


# ---------------------------------------------------------------------------
# Win32 HWND 操作
# ---------------------------------------------------------------------------

def window_rect(hwnd: int) -> Optional[Rect]:
    """指定HWNDのスクリーン矩形を返す."""
    if _USER32 is None or hwnd == 0:
        return None

    rect = _WinRect()
    if _USER32.GetWindowRect(int(hwnd), ctypes.byref(rect)) == 0:
        return None
    return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))


def window_at_point(x: int, y: int) -> int:
    """スクリーン座標の最前面ウィンドウHWNDを返す."""
    if _USER32 is None:
        return 0
    try:
        return int(_USER32.WindowFromPoint(_WinPoint(int(x), int(y))) or 0)
    except Exception:
        logger.debug("WindowFromPointの呼び出しに失敗", exc_info=True)
        return 0


def window_below(hwnd: int) -> int:
    """指定HWNDの背面にある次ウィンドウHWNDを返す."""
    if _USER32 is None or hwnd == 0:
        return 0
    # GW_HWNDNEXT = 2
    try:
        return int(_USER32.GetWindow(int(hwnd), 2) or 0)
    except Exception:
        logger.debug("GetWindowの呼び出しに失敗 (hwnd=%s)", hwnd)
        return 0


def root_window(hwnd: int) -> int:
    """指定HWNDのルートウィンドウHWNDを返す."""
    if _USER32 is None or hwnd == 0:
        return 0
    # GA_ROOT = 2
    try:
        return int(_USER32.GetAncestor(int(hwnd), 2) or 0)
    except Exception:
        logger.debug("GetAncestorの呼び出しに失敗 (hwnd=%s)", hwnd)
        return 0


def window_handle_of(widget: Optional[QWidget]) -> int:
    """QWidgetからHWNDを安全に取得する."""
    if widget is None:
        return 0
    win_id_callable = getattr(widget, "winId", None)
    if not callable(win_id_callable):
        return 0
    try:
        return int(cast(Any, win_id_callable()))
    except Exception:
        logger.debug("winIdの取得に失敗", exc_info=True)
        return 0


def get_foreground_hwnd() -> int:
    """フォアグラウンドウィンドウのHWNDを返す."""
    if _USER32 is None:
        return 0
    return int(_USER32.GetForegroundWindow() or 0)


def get_window_process_id(hwnd: int) -> int:
    """指定HWNDのプロセスIDを返す."""
    if _USER32 is None or hwnd == 0:
        return 0
    process_id = ctypes.c_uint(0)
    _USER32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(process_id))
    return int(process_id.value)


def is_own_process_window(hwnd: int) -> bool:
    """指定HWNDが自プロセスのウィンドウか判定する."""
    if hwnd == 0 or _USER32 is None:
        return False
    return get_window_process_id(hwnd) == os.getpid()
