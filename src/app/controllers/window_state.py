"""MainWindow state persistence controller."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Protocol, Tuple

from src.app.display_modes import clamp_mode_size
from src.core.window_state import WindowState
from src.infra.settings_store import SettingsStore


class _GeometryLike(Protocol):
    """QRect-compatible subset used for state serialization."""

    def width(self) -> int: ...
    def height(self) -> int: ...
    def x(self) -> int: ...
    def y(self) -> int: ...


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
