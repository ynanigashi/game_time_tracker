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
DEFAULT_OVERTIME_ALERT_ENABLED = True
OVERTIME_ALERT_ENABLED_KEY = "overtime_alert_enabled"


class WindowState:
    """ウィンドウ状態の保存/読み込み用クラス."""

    @staticmethod
    def _load_data(path: Path) -> Dict[str, object]:
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
            return {}
        except (OSError, json.JSONDecodeError, ValueError):
            return {}

    @staticmethod
    def _coerce_bool(value: object, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _coerce_int(value: object, default: int) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float, str)):
            try:
                return int(value)
            except (ValueError, TypeError):
                return default
        return default

    @staticmethod
    def load_all(path: Path) -> Tuple[int, int, str, Dict[str, Tuple[int, int]], bool]:
        """保存ファイルから(x, y, display_mode, mode_sizes, overtime_alert_enabled)を読み込む."""
        if not path.exists():
            return (
                0,
                0,
                "max",
                dict(MODE_DEFAULT_SIZES),
                DEFAULT_OVERTIME_ALERT_ENABLED,
            )

        try:
            data = WindowState._load_data(path)
            x = WindowState._coerce_int(data.get("x", 0), 0)
            y = WindowState._coerce_int(data.get("y", 0), 0)

            mode_raw = data.get("display_mode", "max")
            mode = mode_raw if isinstance(mode_raw, str) else "max"

            if mode not in DISPLAY_MODES:
                mode = "max"

            mode_sizes: Dict[str, Tuple[int, int]] = {}
            mode_sizes_raw_obj = data.get("mode_sizes", {})
            mode_sizes_raw: Dict[str, object] = (
                mode_sizes_raw_obj if isinstance(mode_sizes_raw_obj, dict) else {}
            )
            for key in DISPLAY_MODES:
                size_value = mode_sizes_raw.get(key)
                if (
                    isinstance(size_value, list)
                    and len(size_value) == 2
                ):
                    try:
                        mode_sizes[key] = (
                            int(size_value[0]),
                            int(size_value[1]),
                        )
                    except (ValueError, TypeError):
                        mode_sizes[key] = MODE_DEFAULT_SIZES[key]
                else:
                    mode_sizes[key] = MODE_DEFAULT_SIZES[key]

            overtime_alert_enabled = WindowState._coerce_bool(
                data.get(OVERTIME_ALERT_ENABLED_KEY),
                DEFAULT_OVERTIME_ALERT_ENABLED,
            )

            return (x, y, mode, mode_sizes, overtime_alert_enabled)
        except (OSError, json.JSONDecodeError, ValueError):
            return (
                0,
                0,
                "max",
                dict(MODE_DEFAULT_SIZES),
                DEFAULT_OVERTIME_ALERT_ENABLED,
            )

    @staticmethod
    def load(path: Path) -> Tuple[int, int, str, Dict[str, Tuple[int, int]]]:
        """保存ファイルから(x, y, display_mode, mode_sizes)を読み込む."""
        x, y, mode, mode_sizes, _ = WindowState.load_all(path)
        return x, y, mode, mode_sizes

    @staticmethod
    def load_overtime_alert_enabled(path: Path) -> bool:
        """時間超過防止アラート設定を読み込む（未設定時はTrue）。"""
        _, _, _, _, overtime_alert_enabled = WindowState.load_all(path)
        return overtime_alert_enabled

    @staticmethod
    def save(
        path: Path,
        x: int,
        y: int,
        display_mode: str,
        mode_sizes: Dict[str, Tuple[int, int]],
        overtime_alert_enabled: bool = DEFAULT_OVERTIME_ALERT_ENABLED,
    ) -> None:
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
                OVERTIME_ALERT_ENABLED_KEY: bool(overtime_alert_enabled),
            }
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("ウィンドウ状態の保存に失敗しました: %s", e)
        except (ValueError, KeyError) as e:
            logger.error("ウィンドウ状態データの変換に失敗しました: %s", e)
