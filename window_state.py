"""ウィンドウ状態の保存/読み込み."""

import json
import logging
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# 表示モード定数
DISPLAY_MODES = ("max", "mid", "min")
MODE_DEFAULT_SIZES = {
    "max": (480, 400),
    "mid": (480, 300),
    "min": (320, 180),
}


class WindowState:
    """ウィンドウ状態の保存/読み込み用クラス."""

    @staticmethod
    def load(path: Path) -> Tuple[int, int, str, Dict[str, Tuple[int, int]]]:
        """保存ファイルから(x, y, display_mode, mode_sizes)を読み込む."""
        if not path.exists():
            return (0, 0, "max", dict(MODE_DEFAULT_SIZES))
        
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            x = int(data.get("x", 0))
            y = int(data.get("y", 0))
            mode = data.get("display_mode", "max")
            
            # display_mode の検証（不正値の場合はデフォルトに戻す）
            if mode not in DISPLAY_MODES:
                mode = "max"
            
            mode_sizes: Dict[str, Tuple[int, int]] = {}
            mode_sizes_raw = data.get("mode_sizes", {})
            for key in DISPLAY_MODES:
                if key in mode_sizes_raw and isinstance(mode_sizes_raw[key], list) and len(mode_sizes_raw[key]) == 2:
                    try:
                        mode_sizes[key] = (int(mode_sizes_raw[key][0]), int(mode_sizes_raw[key][1]))
                    except (ValueError, TypeError):
                        mode_sizes[key] = MODE_DEFAULT_SIZES[key]
                else:
                    mode_sizes[key] = MODE_DEFAULT_SIZES[key]
            
            return (x, y, mode, mode_sizes)
        except (OSError, json.JSONDecodeError, ValueError):
            return (0, 0, "max", dict(MODE_DEFAULT_SIZES))
    
    @staticmethod
    def save(path: Path, x: int, y: int, display_mode: str, mode_sizes: Dict[str, Tuple[int, int]]) -> None:
        """現在の状態をファイルに保存."""
        try:
            mode_sizes_serialized = {k: [v[0], v[1]] for k, v in mode_sizes.items()}
            data = {
                "x": x,
                "y": y,
                "width": mode_sizes[display_mode][0],
                "height": mode_sizes[display_mode][1],
                "display_mode": display_mode,
                "mode_sizes": mode_sizes_serialized,
            }
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning(f"ウィンドウ状態の保存に失敗しました: {e}")
        except (ValueError, KeyError) as e:
            logger.error(f"ウィンドウ状態データの変換に失敗しました: {e}")
