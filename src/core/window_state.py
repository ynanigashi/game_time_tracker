"""Window state serialization helpers."""

import json
import logging
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

DISPLAY_MODES = ("max", "mid", "min")
MODE_DEFAULT_SIZES = {
    "max": (480, 400),
    "mid": (480, 300),
    "min": (320, 180),
}
DEFAULT_OVERTIME_ALERT_ENABLED = True
DEFAULT_STARTUP_WINDOW_VISIBLE = False
DEFAULT_TRAY_OVERLAY_ENABLED = False
OVERTIME_ALERT_ENABLED_KEY = "overtime_alert_enabled"
STARTUP_WINDOW_VISIBLE_KEY = "startup_window_visible"
TRAY_OVERLAY_ENABLED_KEY = "tray_overlay_enabled"
OVERLAY_POSITION_KEY = "overlay_position"


class WindowState:
    """Load and save persisted window state."""

    @staticmethod
    def _default_state() -> Tuple[int, int, str, Dict[str, Tuple[int, int]], bool]:
        return (
            0,
            0,
            "max",
            dict(MODE_DEFAULT_SIZES),
            DEFAULT_OVERTIME_ALERT_ENABLED,
        )

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
        """Load x, y, display mode, mode sizes, and alert setting from a file."""
        if not path.exists():
            return WindowState._default_state()

        try:
            return WindowState.load_all_from_data(WindowState._load_data(path))
        except (OSError, json.JSONDecodeError, ValueError):
            return WindowState._default_state()

    @staticmethod
    def load_all_from_data(
        data: Dict[str, object],
    ) -> Tuple[int, int, str, Dict[str, Tuple[int, int]], bool]:
        """Load x, y, display mode, mode sizes, and alert setting from a dict."""
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
            if isinstance(size_value, list) and len(size_value) == 2:
                try:
                    mode_sizes[key] = (int(size_value[0]), int(size_value[1]))
                except (ValueError, TypeError):
                    mode_sizes[key] = MODE_DEFAULT_SIZES[key]
            else:
                mode_sizes[key] = MODE_DEFAULT_SIZES[key]

        overtime_alert_enabled = WindowState._coerce_bool(
            data.get(OVERTIME_ALERT_ENABLED_KEY),
            DEFAULT_OVERTIME_ALERT_ENABLED,
        )

        return (x, y, mode, mode_sizes, overtime_alert_enabled)

    @staticmethod
    def to_data(
        x: int,
        y: int,
        display_mode: str,
        mode_sizes: Dict[str, Tuple[int, int]],
        overtime_alert_enabled: bool = DEFAULT_OVERTIME_ALERT_ENABLED,
        startup_window_visible: bool = DEFAULT_STARTUP_WINDOW_VISIBLE,
        tray_overlay_enabled: bool = DEFAULT_TRAY_OVERLAY_ENABLED,
        overlay_position: Tuple[int, int] | None = None,
    ) -> Dict[str, object]:
        mode_sizes_serialized = {k: [v[0], v[1]] for k, v in mode_sizes.items()}
        data: Dict[str, object] = {
            "x": x,
            "y": y,
            "width": mode_sizes[display_mode][0],
            "height": mode_sizes[display_mode][1],
            "display_mode": display_mode,
            "mode_sizes": mode_sizes_serialized,
            OVERTIME_ALERT_ENABLED_KEY: bool(overtime_alert_enabled),
            STARTUP_WINDOW_VISIBLE_KEY: bool(startup_window_visible),
            TRAY_OVERLAY_ENABLED_KEY: bool(tray_overlay_enabled),
        }
        if overlay_position is not None:
            data[OVERLAY_POSITION_KEY] = [int(overlay_position[0]), int(overlay_position[1])]
        return data

    @staticmethod
    def load(path: Path) -> Tuple[int, int, str, Dict[str, Tuple[int, int]]]:
        """Load x, y, display mode, and mode sizes from a file."""
        x, y, mode, mode_sizes, _ = WindowState.load_all(path)
        return x, y, mode, mode_sizes

    @staticmethod
    def load_overtime_alert_enabled(path: Path) -> bool:
        """Load the overtime alert setting. Defaults to True."""
        _, _, _, _, overtime_alert_enabled = WindowState.load_all(path)
        return overtime_alert_enabled

    @staticmethod
    def load_startup_window_visible_from_data(data: Dict[str, object]) -> bool:
        return WindowState._coerce_bool(
            data.get(STARTUP_WINDOW_VISIBLE_KEY),
            DEFAULT_STARTUP_WINDOW_VISIBLE,
        )

    @staticmethod
    def load_tray_overlay_enabled_from_data(data: Dict[str, object]) -> bool:
        return WindowState._coerce_bool(
            data.get(TRAY_OVERLAY_ENABLED_KEY),
            DEFAULT_TRAY_OVERLAY_ENABLED,
        )

    @staticmethod
    def load_overlay_position_from_data(data: Dict[str, object]) -> Tuple[int, int] | None:
        value = data.get(OVERLAY_POSITION_KEY)
        if not isinstance(value, list) or len(value) != 2:
            return None
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def load_startup_window_visible(path: Path) -> bool:
        return WindowState.load_startup_window_visible_from_data(
            WindowState._load_data(path)
        )

    @staticmethod
    def load_tray_overlay_enabled(path: Path) -> bool:
        return WindowState.load_tray_overlay_enabled_from_data(
            WindowState._load_data(path)
        )

    @staticmethod
    def load_overlay_position(path: Path) -> Tuple[int, int] | None:
        return WindowState.load_overlay_position_from_data(WindowState._load_data(path))

    @staticmethod
    def save(
        path: Path,
        x: int,
        y: int,
        display_mode: str,
        mode_sizes: Dict[str, Tuple[int, int]],
        overtime_alert_enabled: bool = DEFAULT_OVERTIME_ALERT_ENABLED,
        startup_window_visible: bool = DEFAULT_STARTUP_WINDOW_VISIBLE,
        tray_overlay_enabled: bool = DEFAULT_TRAY_OVERLAY_ENABLED,
        overlay_position: Tuple[int, int] | None = None,
    ) -> None:
        """Save current window state to a file."""
        try:
            data = WindowState.to_data(
                x,
                y,
                display_mode,
                mode_sizes,
                overtime_alert_enabled=overtime_alert_enabled,
                startup_window_visible=startup_window_visible,
                tray_overlay_enabled=tray_overlay_enabled,
                overlay_position=overlay_position,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("failed to save window state: %s", e)
        except (ValueError, KeyError) as e:
            logger.error("failed to serialize window state: %s", e)
