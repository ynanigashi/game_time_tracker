"""Cover detection for the main-window today-time display."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from src.app.win32_helpers import Point, Rect, is_own_process_window


class Win32CoverDetector:
    """Detects whether foreign windows cover the today-time display."""

    def __init__(
        self,
        owner: "MainWindow",
        *,
        sample_ratios: Sequence[Tuple[float, float]],
        covered_points_threshold: int,
    ) -> None:
        self.owner = owner
        self.sample_ratios = tuple(sample_ratios)
        self.covered_points_threshold = int(covered_points_threshold)

    def is_own_window(self, hwnd: int) -> bool:
        if hwnd == 0:
            return False
        if is_own_process_window(hwnd):
            return True
        hwnd_root = self.owner._root_window(hwnd)
        main_hwnd = self.owner._root_window(self.owner._window_handle_of(self.owner))
        overlay_hwnd = self.owner._root_window(
            self.owner._window_handle_of(self.owner.overlay_window)
        )
        return hwnd_root in {main_hwnd, overlay_hwnd}

    def native_scale_factor(self) -> float:
        hwnd = self.owner._window_handle_of(self.owner)
        rect = self.owner._window_rect(hwnd)
        frame_geometry = self.owner.frameGeometry()
        logical_w = frame_geometry.width()
        logical_h = frame_geometry.height()
        if rect is None or logical_w <= 0 or logical_h <= 0:
            return 1.0

        native_w = max(1, rect[2] - rect[0])
        native_h = max(1, rect[3] - rect[1])
        scale_x = native_w / logical_w
        scale_y = native_h / logical_h
        scale = (scale_x + scale_y) / 2.0
        if 0.75 <= scale <= 3.0:
            return scale
        return 1.0

    def to_native_point(self, x: int, y: int) -> Point:
        hwnd = self.owner._window_handle_of(self.owner)
        native_rect = self.owner._window_rect(hwnd)
        if native_rect is None:
            scale = self.native_scale_factor()
            return int(round(x * scale)), int(round(y * scale))

        frame_geometry = self.owner.frameGeometry()
        logical_w = frame_geometry.width()
        logical_h = frame_geometry.height()
        if logical_w <= 0 or logical_h <= 0:
            return x, y

        native_w = max(1, native_rect[2] - native_rect[0])
        native_h = max(1, native_rect[3] - native_rect[1])
        scale_x = native_w / logical_w
        scale_y = native_h / logical_h
        if not (0.75 <= scale_x <= 3.0 and 0.75 <= scale_y <= 3.0):
            return x, y

        return (
            int(round(native_rect[0] + (x - frame_geometry.x()) * scale_x)),
            int(round(native_rect[1] + (y - frame_geometry.y()) * scale_y)),
        )

    def to_native_rect(self, rect: Rect) -> Rect:
        left_top = self.owner._to_native_point(rect[0], rect[1])
        right_bottom = self.owner._to_native_point(rect[2], rect[3])
        return (
            min(left_top[0], right_bottom[0]),
            min(left_top[1], right_bottom[1]),
            max(left_top[0], right_bottom[0]),
            max(left_top[1], right_bottom[1]),
        )

    def foreground_rect_if_foreign(self, foreground_hwnd: int) -> Optional[Rect]:
        if foreground_hwnd == 0 or self.owner._is_own_window(foreground_hwnd):
            return None
        return self.owner._window_rect(foreground_hwnd)

    def find_covering_foreign_window_at_point(
        self,
        x: int,
        y: int,
        *,
        expected_root_hwnd: Optional[int] = None,
    ) -> int:
        hwnd = self.owner._window_at_point(x, y)
        if hwnd == 0:
            return 0

        if self.owner._is_own_window(hwnd):
            return 0
        hwnd_rect = self.owner._window_rect(hwnd)
        if hwnd_rect is None or not self.owner._rect_contains_point(hwnd_rect, x, y):
            return 0

        candidate_root = self.owner._root_window(hwnd) or hwnd
        if expected_root_hwnd is not None and candidate_root != expected_root_hwnd:
            return 0
        return hwnd

    def get_today_display_cover_state(self) -> Tuple[bool, str]:
        target = self.owner._get_today_time_display()
        if target is None:
            return False, "target_missing"

        target_rect = self.owner._global_rect_of_widget(target)
        if target_rect is None:
            return False, "target_rect_missing"

        sample_points = self.owner._sample_points_from_rect(target_rect)

        def count_covering_foreign_points(*, use_native_points: bool) -> int:
            return sum(
                1
                for x, y in sample_points
                if self.owner._find_covering_foreign_window_at_point(
                    *(self.owner._to_native_point(x, y) if use_native_points else (x, y))
                )
                != 0
            )

        covered_points = count_covering_foreign_points(use_native_points=True)
        if covered_points >= self.covered_points_threshold:
            return True, "covered_native_points"
        if covered_points > 0:
            return False, "covered_native_points_below_threshold"

        covered_points = count_covering_foreign_points(use_native_points=False)
        if covered_points >= self.covered_points_threshold:
            return True, "covered_logical_points"
        if covered_points > 0:
            return False, "covered_logical_points_below_threshold"

        return False, "no_cover_detected"

    def is_today_display_covered(self) -> bool:
        covered, _ = self.get_today_display_cover_state()
        return covered


def sample_points_from_rect(
    rect: Rect,
    sample_ratios: Sequence[Tuple[float, float]],
) -> list[Point]:
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    return [
        (int(left + width * ratio_x), int(top + height * ratio_y))
        for ratio_x, ratio_y in sample_ratios
    ]
