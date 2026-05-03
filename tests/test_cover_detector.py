import unittest
from types import SimpleNamespace

from src.app.cover_detector import CoverDetectorOps, Win32CoverDetector


class Win32CoverDetectorTest(unittest.TestCase):
    def test_find_covering_window_uses_injected_ops(self):
        owner = SimpleNamespace(overlay_window=None)
        detector = Win32CoverDetector(
            owner,
            sample_ratios=((0.5, 0.5),),
            covered_points_threshold=1,
            ops=CoverDetectorOps(
                window_at_point=lambda _x, _y: 500,
                window_rect=lambda _hwnd: (0, 0, 1000, 1000),
                rect_contains_point=lambda _rect, _x, _y: True,
                root_window=lambda hwnd: hwnd,
                window_handle_of=lambda _widget: 0,
            ),
        )

        self.assertEqual(detector.find_covering_foreign_window_at_point(100, 200), 500)

    def test_owner_override_is_used_for_compatibility(self):
        owner = SimpleNamespace(
            _to_native_point=lambda x, y: (x + 1, y + 2),
            overlay_window=None,
        )
        detector = Win32CoverDetector(
            owner,
            sample_ratios=((0.5, 0.5),),
            covered_points_threshold=1,
        )

        self.assertEqual(detector.to_native_point(10, 20), (11, 22))

    def test_target_widget_provider_is_used_for_cover_state(self):
        detector = Win32CoverDetector(
            SimpleNamespace(isVisible=lambda: False, overlay_window=None),
            sample_ratios=((0.5, 0.5),),
            covered_points_threshold=1,
            target_widget_provider=lambda: "target",
            ops=CoverDetectorOps(
                global_rect_of_widget=lambda widget: (0, 0, 10, 10)
                if widget == "target"
                else None,
                sample_points_from_rect=lambda _rect: [],
            ),
        )

        self.assertEqual(
            detector.get_today_display_cover_state(),
            (False, "no_cover_detected"),
        )


if __name__ == "__main__":
    unittest.main()
