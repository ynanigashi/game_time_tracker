"""Temporary legacy aliases for MainWindow private APIs.

This file exists only to keep legacy ``window._foo()`` callers green during the
phase 2 to phase 3 migration. It MUST be removed before phase 3 is merged.
Remaining callers are MainWindow lifecycle methods, collaborator-to-collaborator
callbacks routed through the owner, and MainWindow-focused tests.
"""

from __future__ import annotations

from typing import Any, Optional


class StateAlias:
    """Descriptor that forwards a known state attribute to state access."""

    def __init__(self, state_attr: str) -> None:
        self._state_attr = state_attr

    def __get__(self, instance: Optional[object], owner: type) -> Any:
        if instance is None:
            return self
        if "_state_access" not in instance.__dict__:
            instance._initialize_collaborators()
        return getattr(instance._state_access, self._state_attr)

    def __set__(self, instance: object, value: Any) -> None:
        if "_state_access" not in instance.__dict__:
            instance._initialize_collaborators()
        setattr(instance._state_access, self._state_attr, value)


class CollaboratorMethodAlias:
    """Descriptor that forwards a known MainWindow method to a collaborator."""

    def __init__(self, collaborator_attr: str, method_name: str) -> None:
        self._collaborator_attr = collaborator_attr
        self._method_name = method_name

    def __get__(self, instance: Optional[object], owner: type) -> Any:
        if instance is None:
            return self
        if self._collaborator_attr not in instance.__dict__:
            instance._initialize_collaborators()
        collaborator = getattr(instance, self._collaborator_attr)
        return getattr(collaborator, self._method_name)


def state_aliases() -> dict[str, StateAlias]:
    return {
        name: StateAlias(name)
        for name in (
            "games",
            "active_games_cache",
            "inactive_games_cache",
            "latest_window_titles",
            "overtime_alert_enabled",
            "_overtime_alert_tracker",
            "_overtime_alert_toggle_connected",
            "display_mode",
            "mode_sizes",
            "startup_window_visible",
            "tray_overlay_enabled",
            "overlay_position",
            "_report_dialog",
            "_game_catalog_dialog",
            "_manual_record_dialog",
            "_settings_dialog",
            "_report_button_connected",
            "_manual_record_button_connected",
            "_window_title_copy_connected",
            "_window_title_context_menu_connected",
            "_is_quitting",
            "_force_startup_window_visible",
            "_tray_show_action",
            "_tray_hide_action",
            "_tray_startup_show_action",
            "_tray_startup_hide_action",
            "_tray_overlay_action",
            "_scan_timer",
            "_ui_timer",
        )
    }


def method_aliases() -> dict[str, CollaboratorMethodAlias]:
    mapping = {
        "_controllers": (
            "_get_ui_controller",
            "_get_display_controller",
            "_get_state_controller",
            "_get_loop_controller",
            "_get_overlay_controller",
            "_get_tray_controller",
            "_get_dialog_controller",
            "_get_context_menu_controller",
            "_get_window_title_controller",
            "_get_cover_detector",
            "_get_scan_controller",
            "_get_overtime_alert_controller",
        ),
        "_actions": (
            "_record_playing_games_before_close",
            "_iter_recordable_games",
            "_start_timer",
            "_disable_with_status",
            "_init_components",
            "_save_window_state",
            "_set_status",
            "_initialize_overlay",
            "_is_overtime_alert_enabled",
            "_set_overtime_alert_enabled",
            "_get_overtime_alert_tracker",
            "_get_overtime_alert_toggle",
            "_get_report_button",
            "_get_manual_record_button",
            "_initialize_overtime_alert_toggle",
            "_initialize_report_button",
            "_initialize_manual_record_button",
            "_open_report_dialog",
            "_open_manual_record_dialog",
            "_get_or_create_manual_record_dialog",
            "_save_manual_record",
            "_refresh_after_manual_record",
            "_reload_today_stats",
            "_set_today_stats_cache",
            "_open_settings_dialog",
            "_open_game_catalog_dialog",
            "_on_game_catalog_saved",
            "_on_settings_saved",
            "_on_overtime_alert_toggled",
            "_prime_overtime_alert_progress",
            "_emit_overtime_alert",
            "_update_overtime_alert",
            "_get_overlay_window",
            "_get_today_time_display",
            "_refresh_overlay_time",
            "_sync_overlay_geometry",
            "_should_show_overlay",
            "_sync_overlay_visibility",
            "_sync_overlay",
            "_close_overlay",
            "_apply_mode_geometry",
            "_apply_display_mode",
            "_set_widget_visibility",
            "_set_widget_with_height",
            "_should_cycle_display_mode",
            "_should_show_context_menu",
            "_show_context_menu",
            "_add_display_mode_menu",
            "_handle_context_menu_selection",
            "_set_display_mode",
            "_cycle_display_mode",
            "_record_current_mode_size",
        ),
        "_scan_ops": (
            "_scan_tick",
            "_scan_games",
            "_apply_scan_result",
            "_update_scan_status",
            "_update_active_list",
            "_all_playing_games",
            "_has_playing_games",
            "_update_session_times",
            "_update_today_totals",
            "_update_window_list",
            "_load_today_game_minutes",
            "_update_today_games_list",
            "_load_today_completed_seconds",
        ),
        "_tray_title_ops": (
            "_initialize_tray_icon",
            "_build_tray_menu",
            "_show_main_window_from_tray",
            "_process_pending_ui_events",
            "_align_today_display_to_overlay_position",
            "_hide_main_window_to_tray",
            "_sync_tray_window_actions",
            "_set_startup_window_visible",
            "_set_tray_overlay_enabled",
            "_quit_application",
            "should_show_window_on_startup",
            "_get_window_list_widget",
            "_initialize_window_title_copy",
            "_initialize_window_title_context_menu",
            "_on_window_title_item_clicked",
            "_show_window_title_context_menu",
            "_window_title_item_at",
            "_text_from_window_title_item",
            "_copy_text_to_clipboard",
        ),
        "_win32_ops": (
            "_global_rect_of_widget",
            "_window_rect",
            "_rect_contains_point",
            "_rects_intersect",
            "_sample_points_from_rect",
            "_window_at_point",
            "_window_below",
            "_root_window",
            "_window_handle_of",
            "_is_own_window",
            "_native_scale_factor",
            "_to_native_point",
            "_to_native_rect",
            "_foreground_rect_if_foreign",
            "_find_covering_foreign_window_at_point",
            "_get_today_display_cover_state",
            "_is_today_display_covered_by_foreground_window",
        ),
    }
    return {
        name: CollaboratorMethodAlias(collaborator_attr, name)
        for collaborator_attr, names in mapping.items()
        for name in names
    }
