"""Controller provider methods installed on MainWindow."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMenu

from src.app.controllers import (
    MainWindowContextMenuController,
    MainWindowDialogController,
    MainWindowDisplayController,
    MainWindowLoopController,
    MainWindowOverlayController,
    MainWindowOvertimeAlertController,
    MainWindowScanController,
    MainWindowStateController,
    MainWindowTitleController,
    MainWindowTrayController,
    MainWindowUiController,
)
from src.app.cover_detector import CoverDetectorOps, Win32CoverDetector
from src.app.main_constants import (
    BASE_TITLE,
    MAX_WIDGET_HEIGHT,
    OVERLAY_COVERED_POINTS_THRESHOLD,
    OVERLAY_SAMPLE_RATIOS,
)
from src.app.main_window.base import MainWindowCollaborator
from src.core.window_state import DISPLAY_MODES
from src.infra.runtime_paths import resolve_window_state_file
from src.ui.game_catalog_dialog import GameCatalogDialog
from src.ui.manual_record_dialog import ManualRecordDialog
from src.ui.report_dialog import ReportDialog
from src.ui.settings_dialog import SettingsDialog


class MainWindowControllerRegistry(MainWindowCollaborator):
    """Controller factory methods for MainWindow."""

    def _get_ui_controller(self) -> MainWindowUiController:
        daily_stats = self._owner._ensure_daily_stats()
        return self._owner._resolve_dependency(
            "_ui_controller",
            factory=lambda: MainWindowUiController(self._owner.w, daily_stats),
            validator=lambda controller: (
                controller.w is self._owner.w and controller.daily_stats is daily_stats
            ),
        )

    def _get_display_controller(self) -> MainWindowDisplayController:
        return self._owner._resolve_dependency(
            "_display_controller",
            factory=lambda: MainWindowDisplayController(MAX_WIDGET_HEIGHT),
        )

    def _get_state_controller(self) -> MainWindowStateController:
        return self._owner._resolve_dependency(
            "_state_controller",
            factory=lambda: MainWindowStateController(resolve_window_state_file()),
        )

    def _get_loop_controller(self) -> MainWindowLoopController:
        return self._owner._resolve_dependency(
            "_loop_controller",
            factory=lambda: MainWindowLoopController(
                timer_factory=QTimer
            ),
        )

    def _get_overlay_controller(self) -> MainWindowOverlayController:
        return self._owner._resolve_dependency(
            "_overlay_controller",
            factory=lambda: MainWindowOverlayController(
                overlay_window_provider=lambda: self._owner._get_overlay_window(),
                set_overlay_window=lambda window: setattr(self._owner, "overlay_window", window),
                set_overlay_position=lambda position: setattr(
                    self._state,
                    "overlay_position",
                    position,
                ),
                get_overlay_position=lambda: self._state.overlay_position,
                today_time_display_provider=lambda: self._owner._get_today_time_display(),
                save_window_state=lambda: self._owner._save_window_state(),
                has_playing_games=lambda: self._owner._has_playing_games(),
                today_display_cover_state=lambda: self._owner._get_today_display_cover_state(),
                is_own_window=lambda hwnd: self._owner._is_own_window(hwnd),
                is_main_window_visible=lambda: bool(
                    getattr(self._owner, "isVisible", lambda: False)()
                ),
                is_main_window_active=lambda: bool(
                    getattr(self._owner, "isActiveWindow", lambda: False)()
                ),
                is_active_window_own=lambda active_window: active_window is self._owner,
                window_geometry=self._owner.geometry,
                move_window=self._owner.move,
                get_tray_overlay_enabled=lambda: bool(self._state.tray_overlay_enabled),
            ),
            validator=lambda controller: (
                getattr(controller.window_geometry, "__self__", None) is self._owner
                and getattr(controller.move_window, "__self__", None) is self._owner
            ),
        )

    def _get_tray_controller(self) -> MainWindowTrayController:
        return self._owner._resolve_dependency(
            "_tray_controller",
            factory=lambda: MainWindowTrayController(
                parent_widget=self._owner,
                base_title=BASE_TITLE,
                action_state=self._state._ensure_tray_action_state(),
                get_tray_overlay_enabled=lambda: bool(self._state.tray_overlay_enabled),
                set_tray_overlay_enabled_value=lambda enabled: setattr(
                    self._state,
                    "tray_overlay_enabled",
                    bool(enabled),
                ),
                get_startup_window_visible=lambda: bool(self._state.startup_window_visible),
                set_startup_window_visible_value=lambda visible: setattr(
                    self._state,
                    "startup_window_visible",
                    bool(visible),
                ),
                get_force_startup_window_visible=lambda: bool(
                    self._state._force_startup_window_visible
                ),
                get_overlay_position=lambda: self._state.overlay_position,
                get_tray_icon=lambda: getattr(self._owner, "tray_icon", None),
                set_tray_icon=lambda icon: setattr(self._owner, "tray_icon", icon),
                set_tray_menu=lambda menu: setattr(self._owner, "tray_menu", menu),
                show_window=self._owner.show,
                hide_window=self._owner.hide,
                raise_window=self._owner.raise_,
                activate_window=self._owner.activateWindow,
                is_window_visible=lambda: bool(self._owner.isVisible()),
                window_geometry=self._owner.geometry,
                move_window=self._owner.move,
                open_manual_record_dialog=self._owner._open_manual_record_dialog,
                open_report_dialog=self._owner._open_report_dialog,
                open_game_catalog_dialog=self._owner._open_game_catalog_dialog,
                open_settings_dialog=self._owner._open_settings_dialog,
                sync_tray_window_actions_callback=self._owner._sync_tray_window_actions,
                save_window_state=self._owner._save_window_state,
                sync_overlay=self._owner._sync_overlay,
                set_force_startup_window_visible=lambda visible: setattr(
                    self._state,
                    "_force_startup_window_visible",
                    bool(visible),
                ),
                process_pending_ui_events_callback=self._owner._process_pending_ui_events,
                align_today_display_to_overlay_position_callback=(
                    self._owner._align_today_display_to_overlay_position
                ),
                today_time_display_provider=self._owner._get_today_time_display,
                set_quitting=lambda quitting: setattr(
                    self._state,
                    "_is_quitting",
                    bool(quitting),
                ),
                record_playing_games_before_close=(
                    self._owner._record_playing_games_before_close
                ),
                close_overlay=self._owner._close_overlay,
            ),
            validator=lambda controller: (
                controller.parent_widget is self._owner
                and controller.action_state is self._state._ensure_tray_action_state()
            ),
        )

    def _get_dialog_controller(self) -> MainWindowDialogController:
        return self._owner._resolve_dependency(
            "_dialog_controller",
            factory=lambda: MainWindowDialogController(
                parent_widget=self._owner,
                report_dialog_cls=ReportDialog,
                manual_record_dialog_cls=ManualRecordDialog,
                game_catalog_dialog_cls=GameCatalogDialog,
                settings_dialog_cls=SettingsDialog,
                state=self._state._ensure_dialog_state(),
                has_recorder=lambda: hasattr(self._owner, "recorder"),
                log_handler_provider=lambda: self._owner.recorder.log_handler,
                record_with_times=lambda game, start_time, end_time: (
                    self._owner.recorder.record_with_times(game, start_time, end_time)
                ),
                games_provider=lambda: self._state.games,
                get_today_stats=lambda: self._owner.recorder.log_handler.get_today_stats(),
                set_today_stats=self._owner._set_today_stats_cache,
                set_disabled=lambda disabled: self._owner.setDisabled(disabled),
                get_report_button=self._owner._get_report_button,
                get_manual_record_button=self._owner._get_manual_record_button,
                open_report_dialog_callback=self._owner._open_report_dialog,
                open_manual_record_dialog_callback=self._owner._open_manual_record_dialog,
                set_status=self._owner._set_status,
                active_games_provider=lambda: self._state.active_games_cache,
                update_today_totals=self._owner._update_today_totals,
                update_today_games_list=self._owner._update_today_games_list,
                update_overtime_alert=self._owner._update_overtime_alert,
                sync_overlay=self._owner._sync_overlay,
                on_settings_saved_callback=self._owner._on_settings_saved,
                on_game_catalog_saved_callback=self._owner._on_game_catalog_saved,
                init_components=self._owner._init_components,
            ),
            validator=lambda controller: (
                controller.parent_widget is self._owner
                and controller.state is self._state._ensure_dialog_state()
            ),
        )

    def _get_context_menu_controller(self) -> MainWindowContextMenuController:
        return self._owner._resolve_dependency(
            "_context_menu_controller",
            factory=lambda: MainWindowContextMenuController(
                parent_widget=self._owner,
                display_modes=DISPLAY_MODES,
                display_mode_provider=lambda: self._state.display_mode,
                set_display_mode=self._owner._set_display_mode,
                open_manual_record_dialog=self._owner._open_manual_record_dialog,
                open_report_dialog=self._owner._open_report_dialog,
                open_game_catalog_dialog=self._owner._open_game_catalog_dialog,
                open_settings_dialog=self._owner._open_settings_dialog,
                quit_application=self._owner._quit_application,
            ),
            validator=lambda controller: controller.parent_widget is self._owner,
        )

    def _get_window_title_controller(self) -> MainWindowTitleController:
        return self._owner._resolve_dependency(
            "_window_title_controller",
            factory=lambda: MainWindowTitleController(
                qmenu_cls=QMenu,
                state=self._state._ensure_window_title_state(),
                get_window_list_widget=lambda: getattr(self._owner.w, "window_list", None),
                on_item_clicked=self._owner._on_window_title_item_clicked,
                show_context_menu=self._owner._show_window_title_context_menu,
                open_game_catalog_dialog=self._owner._open_game_catalog_dialog,
                set_status=self._owner._set_status,
            ),
            validator=lambda controller: (
                controller.state is self._state._ensure_window_title_state()
            ),
        )

    def _get_cover_detector(self) -> Win32CoverDetector:
        return self._owner._resolve_dependency(
            "_cover_detector",
            factory=lambda: Win32CoverDetector(
                self._owner,
                sample_ratios=OVERLAY_SAMPLE_RATIOS,
                covered_points_threshold=OVERLAY_COVERED_POINTS_THRESHOLD,
                target_widget_provider=lambda: self._owner._get_today_time_display(),
                ops=CoverDetectorOps(
                    root_window=self._owner._root_window,
                    window_handle_of=self._owner._window_handle_of,
                    window_rect=self._owner._window_rect,
                    rect_contains_point=lambda rect, x, y: self._owner._rect_contains_point(
                        rect,
                        x,
                        y,
                    ),
                    rects_intersect=lambda first, second: self._owner._rects_intersect(
                        first,
                        second,
                    ),
                    window_at_point=self._owner._window_at_point,
                    window_below=self._owner._window_below,
                    global_rect_of_widget=lambda widget: self._owner._global_rect_of_widget(
                        widget
                    ),
                    sample_points_from_rect=lambda rect: self._owner._sample_points_from_rect(
                        rect
                    ),
                ),
            ),
            validator=lambda detector: detector.owner is self._owner,
        )

    def _get_scan_controller(self) -> MainWindowScanController:
        return self._owner._resolve_dependency(
            "_scan_controller",
            factory=lambda: MainWindowScanController(
                state_tracker=self._owner.state_tracker,
                games_provider=lambda: self._state.games,
                scan_result_updater=lambda active, inactive, titles: (
                    self._state._ensure_session_state().update_scan_result(
                        active_games=active,
                        inactive_games=inactive,
                        window_titles=titles,
                    )
                ),
                update_active_list=self._owner._update_active_list,
                update_window_list=self._owner._update_window_list,
                update_scan_status=self._owner._update_scan_status,
                set_status=self._owner._set_status,
                load_today_game_minutes=self._owner._load_today_game_minutes,
                get_today_stats=self._owner.recorder.log_handler.get_today_stats,
            ),
            validator=lambda controller: (
                controller.state_tracker is self._owner.state_tracker
            ),
        )

    def _get_overtime_alert_controller(self) -> MainWindowOvertimeAlertController:
        return self._owner._resolve_dependency(
            "_overtime_alert_controller",
            factory=lambda: MainWindowOvertimeAlertController(
                self._state._ensure_alert_state(),
                toggle_provider=self._owner._get_overtime_alert_toggle,
                on_toggle_changed=self._owner._on_overtime_alert_toggled,
                active_games_provider=lambda: self._state.active_games_cache,
                inactive_games_provider=lambda: self._state.inactive_games_cache,
                calculate_today_total_seconds=lambda active, inactive, now: (
                    self._owner._get_ui_controller().calculate_today_total_seconds(
                        active,
                        inactive,
                        now,
                    )
                ),
                sync_overlay=self._owner._sync_overlay,
            ),
            validator=lambda controller: (
                controller.state is self._state._ensure_alert_state()
            ),
        )
