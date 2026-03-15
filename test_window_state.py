# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""window_state.py 縺ｮ繝ｦ繝九ャ繝医ユ繧ｹ繝・"""

import os
import tempfile
import unittest
from pathlib import Path

# 蜈ｱ騾壹せ繧ｿ繝悶ｒ繧､繝ｳ繧ｹ繝医・繝ｫ
from test_stubs import install_stubs
install_stubs()

import window_state
from window_state import WindowState


class TestWindowState(unittest.TestCase):
    """WindowState繧ｯ繝ｩ繧ｹ縺ｮ繝・せ繝・"""

    def setUp(self):
        """繝・せ繝育畑縺ｮ荳譎ゅヵ繧｡繧､繝ｫ繝代せ繧定ｨｭ螳・"""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.test_path = Path(self.temp_dir) / "test_window_state.txt"

    def tearDown(self):
        """繝・せ繝育畑繝輔ぃ繧､繝ｫ繧貞炎髯､."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_nonexistent_file_returns_defaults(self):
        """蟄伜惠縺励↑縺・ヵ繧｡繧､繝ｫ縺ｯ繝・ヵ繧ｩ繝ｫ繝亥､繧定ｿ斐☆."""
        x, y, mode, mode_sizes = WindowState.load(self.test_path)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)
        self.assertEqual(mode, "max")
        self.assertIn("max", mode_sizes)

    def test_save_and_load_roundtrip(self):
        """菫晏ｭ倥→隱ｭ縺ｿ霎ｼ縺ｿ縺ｮ蠕蠕ｩ繝・せ繝・"""
        mode_sizes = {"max": (500, 400), "mid": (450, 300), "min": (300, 150)}
        WindowState.save(self.test_path, 100, 200, "mid", mode_sizes)
        
        x, y, mode, loaded_sizes = WindowState.load(self.test_path)
        self.assertEqual(x, 100)
        self.assertEqual(y, 200)
        self.assertEqual(mode, "mid")
        self.assertEqual(loaded_sizes["mid"], (450, 300))

    def test_load_invalid_mode_falls_back_to_max(self):
        """荳肴ｭ｣縺ｪdisplay_mode縺ｯ'max'縺ｫ繝輔か繝ｼ繝ｫ繝舌ャ繧ｯ."""
        import json
        data = {"x": 50, "y": 50, "display_mode": "invalid_mode", "mode_sizes": {}}
        self.test_path.write_text(json.dumps(data), encoding="utf-8")
        
        x, y, mode, mode_sizes = WindowState.load(self.test_path)
        self.assertEqual(mode, "max")

    def test_load_corrupted_json_returns_defaults(self):
        """遐ｴ謳阪＠縺櫟SON縺ｯ繝・ヵ繧ｩ繝ｫ繝亥､繧定ｿ斐☆."""
        self.test_path.write_text("{invalid json", encoding="utf-8")
        
        x, y, mode, mode_sizes = WindowState.load(self.test_path)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)
        self.assertEqual(mode, "max")

    def test_load_overtime_alert_enabled_defaults_true(self):
        """overtime_alert_enabled未設定時はTrueを返す."""
        mode_sizes = {"max": (500, 400), "mid": (450, 300), "min": (300, 150)}
        WindowState.save(self.test_path, 100, 200, "mid", mode_sizes)

        self.assertTrue(WindowState.load_overtime_alert_enabled(self.test_path))

    def test_save_and_load_overtime_alert_enabled_false(self):
        """overtime_alert_enabled=Falseを保存/復元できる."""
        mode_sizes = {"max": (500, 400), "mid": (450, 300), "min": (300, 150)}
        WindowState.save(
            self.test_path,
            100,
            200,
            "mid",
            mode_sizes,
            overtime_alert_enabled=False,
        )

        self.assertFalse(WindowState.load_overtime_alert_enabled(self.test_path))

    def test_load_all_includes_overtime_alert_enabled(self):
        """load_allはovertime_alert_enabledを含めて返す."""
        mode_sizes = {"max": (500, 400), "mid": (450, 300), "min": (300, 150)}
        WindowState.save(
            self.test_path,
            100,
            200,
            "mid",
            mode_sizes,
            overtime_alert_enabled=False,
        )

        x, y, mode, loaded_sizes, overtime_alert_enabled = WindowState.load_all(self.test_path)

        self.assertEqual((x, y, mode), (100, 200, "mid"))
        self.assertEqual(loaded_sizes["mid"], (450, 300))
        self.assertFalse(overtime_alert_enabled)


if __name__ == "__main__":
    unittest.main()
