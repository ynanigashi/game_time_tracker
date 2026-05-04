"""State accessors for MainWindow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

from src.app.alert_state import GameAlertState
from src.app.dialog_state import DialogRefState
from src.app.display_state import WindowDisplayState
from src.app.lifecycle_state import AppLifecycleState
from src.app.main_constants import OVERTIME_ALERT_THRESHOLDS_MINUTES
from src.app.session_state import GameSessionState
from src.app.timer_state import TimerState
from src.app.tray_state import TrayActionState
from src.app.window_title_state import WindowTitleState
from src.core.window_state import DEFAULT_OVERTIME_ALERT_ENABLED, MODE_DEFAULT_SIZES

if TYPE_CHECKING:
    from src.app.controllers import OvertimeAlertTracker
    from src.core.models import GameEntry
    from src.ui.game_catalog_dialog import GameCatalogDialog
    from src.ui.manual_record_dialog import ManualRecordDialog
    from src.ui.report_dialog import ReportDialog
    from src.ui.settings_dialog import SettingsDialog


class MainWindowStateDescriptors:
    """Compatibility accessors backed by extracted MainWindow state objects."""

    def _ensure_session_state(self) -> GameSessionState:
        state = getattr(self, "session_state", None)
        if state is None:
            state = GameSessionState()
            self.session_state = state
        return state

    @property
    def games(self) -> List[GameEntry]:
        return self._ensure_session_state().games

    @games.setter
    def games(self, value: Sequence[GameEntry]) -> None:
        self._ensure_session_state().games = list(value)

    @property
    def active_games_cache(self) -> List[GameEntry]:
        return self._ensure_session_state().active_games_cache

    @active_games_cache.setter
    def active_games_cache(self, value: Sequence[GameEntry]) -> None:
        self._ensure_session_state().active_games_cache = list(value)

    @property
    def inactive_games_cache(self) -> List[GameEntry]:
        return self._ensure_session_state().inactive_games_cache

    @inactive_games_cache.setter
    def inactive_games_cache(self, value: Sequence[GameEntry]) -> None:
        self._ensure_session_state().inactive_games_cache = list(value)

    @property
    def latest_window_titles(self) -> List[str]:
        return self._ensure_session_state().latest_window_titles

    @latest_window_titles.setter
    def latest_window_titles(self, value: Sequence[str]) -> None:
        self._ensure_session_state().latest_window_titles = list(value)

    def _ensure_alert_state(self) -> GameAlertState:
        state = getattr(self, "alert_state", None)
        if state is None:
            state = GameAlertState.create(
                enabled=DEFAULT_OVERTIME_ALERT_ENABLED,
                thresholds_minutes=OVERTIME_ALERT_THRESHOLDS_MINUTES,
            )
            self.alert_state = state
        return state

    @property
    def overtime_alert_enabled(self) -> bool:
        return self._ensure_alert_state().overtime_alert_enabled

    @overtime_alert_enabled.setter
    def overtime_alert_enabled(self, value: bool) -> None:
        self._ensure_alert_state().overtime_alert_enabled = bool(value)

    @property
    def _overtime_alert_tracker(self) -> OvertimeAlertTracker:
        return self._ensure_alert_state().overtime_alert_tracker

    @_overtime_alert_tracker.setter
    def _overtime_alert_tracker(self, value: OvertimeAlertTracker) -> None:
        self._ensure_alert_state().overtime_alert_tracker = value

    @property
    def _overtime_alert_toggle_connected(self) -> bool:
        return self._ensure_alert_state().toggle_connected

    @_overtime_alert_toggle_connected.setter
    def _overtime_alert_toggle_connected(self, value: bool) -> None:
        self._ensure_alert_state().toggle_connected = bool(value)

    def _ensure_display_state(self) -> WindowDisplayState:
        state = getattr(self, "display_state", None)
        if state is None:
            state = WindowDisplayState.create()
            self.display_state = state
        return state

    @property
    def display_mode(self) -> str:
        return self._ensure_display_state().display_mode

    @display_mode.setter
    def display_mode(self, value: str) -> None:
        self._ensure_display_state().display_mode = str(value)

    @property
    def mode_sizes(self) -> Dict[str, Tuple[int, int]]:
        return self._ensure_display_state().mode_sizes

    @mode_sizes.setter
    def mode_sizes(self, value: Dict[str, Tuple[int, int]]) -> None:
        self._ensure_display_state().mode_sizes = {
            str(mode): (int(size[0]), int(size[1]))
            for mode, size in value.items()
        }

    @property
    def startup_window_visible(self) -> bool:
        return self._ensure_display_state().startup_window_visible

    @startup_window_visible.setter
    def startup_window_visible(self, value: bool) -> None:
        self._ensure_display_state().startup_window_visible = bool(value)

    @property
    def tray_overlay_enabled(self) -> bool:
        return self._ensure_display_state().tray_overlay_enabled

    @tray_overlay_enabled.setter
    def tray_overlay_enabled(self, value: bool) -> None:
        self._ensure_display_state().tray_overlay_enabled = bool(value)

    @property
    def overlay_position(self) -> Optional[Tuple[int, int]]:
        return self._ensure_display_state().overlay_position

    @overlay_position.setter
    def overlay_position(self, value: Optional[Tuple[int, int]]) -> None:
        if value is None:
            self._ensure_display_state().overlay_position = None
            return
        self._ensure_display_state().overlay_position = (int(value[0]), int(value[1]))

    def _ensure_dialog_state(self) -> DialogRefState:
        state = getattr(self, "dialog_state", None)
        if state is None:
            state = DialogRefState()
            self.dialog_state = state
        return state

    @property
    def _report_dialog(self) -> Optional[ReportDialog]:
        return self._ensure_dialog_state().report_dialog

    @_report_dialog.setter
    def _report_dialog(self, value: Optional[ReportDialog]) -> None:
        self._ensure_dialog_state().report_dialog = value

    @property
    def _game_catalog_dialog(self) -> Optional[GameCatalogDialog]:
        return self._ensure_dialog_state().game_catalog_dialog

    @_game_catalog_dialog.setter
    def _game_catalog_dialog(self, value: Optional[GameCatalogDialog]) -> None:
        self._ensure_dialog_state().game_catalog_dialog = value

    @property
    def _manual_record_dialog(self) -> Optional[ManualRecordDialog]:
        return self._ensure_dialog_state().manual_record_dialog

    @_manual_record_dialog.setter
    def _manual_record_dialog(self, value: Optional[ManualRecordDialog]) -> None:
        self._ensure_dialog_state().manual_record_dialog = value

    @property
    def _settings_dialog(self) -> Optional[SettingsDialog]:
        return self._ensure_dialog_state().settings_dialog

    @_settings_dialog.setter
    def _settings_dialog(self, value: Optional[SettingsDialog]) -> None:
        self._ensure_dialog_state().settings_dialog = value

    @property
    def _report_button_connected(self) -> bool:
        return self._ensure_dialog_state().report_button_connected

    @_report_button_connected.setter
    def _report_button_connected(self, value: bool) -> None:
        self._ensure_dialog_state().report_button_connected = bool(value)

    @property
    def _manual_record_button_connected(self) -> bool:
        return self._ensure_dialog_state().manual_record_button_connected

    @_manual_record_button_connected.setter
    def _manual_record_button_connected(self, value: bool) -> None:
        self._ensure_dialog_state().manual_record_button_connected = bool(value)

    def _ensure_window_title_state(self) -> WindowTitleState:
        state = getattr(self, "window_title_state", None)
        if state is None:
            state = WindowTitleState()
            self.window_title_state = state
        return state

    @property
    def _window_title_copy_connected(self) -> bool:
        return self._ensure_window_title_state().copy_connected

    @_window_title_copy_connected.setter
    def _window_title_copy_connected(self, value: bool) -> None:
        self._ensure_window_title_state().copy_connected = bool(value)

    @property
    def _window_title_context_menu_connected(self) -> bool:
        return self._ensure_window_title_state().context_menu_connected

    @_window_title_context_menu_connected.setter
    def _window_title_context_menu_connected(self, value: bool) -> None:
        self._ensure_window_title_state().context_menu_connected = bool(value)

    def _ensure_lifecycle_state(self) -> AppLifecycleState:
        state = getattr(self, "lifecycle_state", None)
        if state is None:
            state = AppLifecycleState()
            self.lifecycle_state = state
        return state

    @property
    def _is_quitting(self) -> bool:
        if "lifecycle_state" not in self.__dict__:
            return True
        return self._ensure_lifecycle_state().is_quitting

    @_is_quitting.setter
    def _is_quitting(self, value: bool) -> None:
        self._ensure_lifecycle_state().is_quitting = bool(value)

    @property
    def _force_startup_window_visible(self) -> bool:
        return self._ensure_lifecycle_state().force_startup_window_visible

    @_force_startup_window_visible.setter
    def _force_startup_window_visible(self, value: bool) -> None:
        self._ensure_lifecycle_state().force_startup_window_visible = bool(value)

    def _ensure_tray_action_state(self) -> TrayActionState:
        state = getattr(self, "tray_action_state", None)
        if state is None:
            state = TrayActionState()
            self.tray_action_state = state
        return state

    @property
    def _tray_show_action(self) -> object:
        return self._ensure_tray_action_state().show_action

    @_tray_show_action.setter
    def _tray_show_action(self, value: object) -> None:
        self._ensure_tray_action_state().show_action = value

    @property
    def _tray_hide_action(self) -> object:
        return self._ensure_tray_action_state().hide_action

    @_tray_hide_action.setter
    def _tray_hide_action(self, value: object) -> None:
        self._ensure_tray_action_state().hide_action = value

    @property
    def _tray_startup_show_action(self) -> object:
        return self._ensure_tray_action_state().startup_show_action

    @_tray_startup_show_action.setter
    def _tray_startup_show_action(self, value: object) -> None:
        self._ensure_tray_action_state().startup_show_action = value

    @property
    def _tray_startup_hide_action(self) -> object:
        return self._ensure_tray_action_state().startup_hide_action

    @_tray_startup_hide_action.setter
    def _tray_startup_hide_action(self, value: object) -> None:
        self._ensure_tray_action_state().startup_hide_action = value

    @property
    def _tray_overlay_action(self) -> object:
        return self._ensure_tray_action_state().overlay_action

    @_tray_overlay_action.setter
    def _tray_overlay_action(self, value: object) -> None:
        self._ensure_tray_action_state().overlay_action = value

    def _ensure_timer_state(self) -> TimerState:
        state = getattr(self, "timer_state", None)
        if state is None:
            state = TimerState()
            self.timer_state = state
        return state

    @property
    def _scan_timer(self) -> object:
        return self._ensure_timer_state().scan_timer

    @_scan_timer.setter
    def _scan_timer(self, value: object) -> None:
        self._ensure_timer_state().scan_timer = value

    @property
    def _ui_timer(self) -> object:
        return self._ensure_timer_state().ui_timer

    @_ui_timer.setter
    def _ui_timer(self, value: object) -> None:
        self._ensure_timer_state().ui_timer = value


def install_main_window_state_accessors(target_cls: type) -> None:
    """Install state accessors on MainWindow without using inheritance."""
    for name, descriptor in MainWindowStateDescriptors.__dict__.items():
        if name.startswith("__"):
            continue
        setattr(target_cls, name, descriptor)
