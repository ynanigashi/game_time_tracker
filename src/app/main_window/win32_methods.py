"""Win32 and cover-detection delegates for MainWindow."""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtWidgets import QWidget

from src.app.main_constants import OVERLAY_SAMPLE_RATIOS
from src.app.main_window.base import MainWindowCollaborator
from src.app.win32_helpers import (
    get_foreground_hwnd,
    global_rect_of_widget,
    Point,
    Rect,
    rect_contains_point,
    rects_intersect,
    root_window,
    sample_points_from_rect,
    window_at_point,
    window_below,
    window_handle_of,
    window_rect,
)


class MainWindowWin32Ops(MainWindowCollaborator):
    """Expose Win32 helper delegates expected by legacy MainWindow tests."""

    @staticmethod
    def _global_rect_of_widget(widget: QWidget) -> Optional[Rect]:
        return global_rect_of_widget(widget)

    @staticmethod
    def _window_rect(hwnd: int) -> Optional[Rect]:
        return window_rect(hwnd)

    @staticmethod
    def _rect_contains_point(rect: Rect, x: int, y: int) -> bool:
        return rect_contains_point(rect, x, y)

    @staticmethod
    def _rects_intersect(first_rect: Rect, second_rect: Rect) -> bool:
        return rects_intersect(first_rect, second_rect)

    @staticmethod
    def _sample_points_from_rect(rect: Rect) -> List[Point]:
        return sample_points_from_rect(rect, OVERLAY_SAMPLE_RATIOS)

    @staticmethod
    def _window_at_point(x: int, y: int) -> int:
        return window_at_point(x, y)

    @staticmethod
    def _window_below(hwnd: int) -> int:
        return window_below(hwnd)

    @staticmethod
    def _root_window(hwnd: int) -> int:
        return root_window(hwnd)

    @staticmethod
    def _window_handle_of(widget: Optional[QWidget]) -> int:
        return window_handle_of(widget)

    def _is_own_window(self, hwnd: int) -> bool:
        """Return whether HWND belongs to this app or its overlay."""
        return self._controllers._get_cover_detector().is_own_window(hwnd)

    def _native_scale_factor(self) -> float:
        """Estimate logical-to-native coordinate scaling."""
        return self._controllers._get_cover_detector().native_scale_factor()

    def _to_native_point(self, x: int, y: int) -> Point:
        """Convert a logical point to Win32 native coordinates."""
        return self._controllers._get_cover_detector().to_native_point(x, y)

    def _to_native_rect(self, rect: Rect) -> Rect:
        """Convert a logical rectangle to Win32 native coordinates."""
        return self._controllers._get_cover_detector().to_native_rect(rect)

    def _foreground_rect_if_foreign(self) -> Optional[Rect]:
        """Return the foreground rectangle when it belongs to a foreign window."""
        return self._controllers._get_cover_detector().foreground_rect_if_foreign(
            get_foreground_hwnd()
        )

    def _find_covering_foreign_window_at_point(
        self,
        x: int,
        y: int,
        *,
        expected_root_hwnd: Optional[int] = None,
    ) -> int:
        """Return a foreign HWND that covers a point, if any."""
        return self._controllers._get_cover_detector().find_covering_foreign_window_at_point(
            x,
            y,
            expected_root_hwnd=expected_root_hwnd,
        )

    def _get_today_display_cover_state(self) -> Tuple[bool, str]:
        """Return cover state and reason for today_time_display."""
        return self._controllers._get_cover_detector().get_today_display_cover_state()

    def _is_today_display_covered_by_foreground_window(self) -> bool:
        """Return whether today_time_display is covered by a foreign window."""
        return self._controllers._get_cover_detector().is_today_display_covered()
