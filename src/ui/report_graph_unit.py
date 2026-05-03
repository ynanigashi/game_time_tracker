"""Graph unit toggle controller for the report dialog."""

from __future__ import annotations

import logging
from time import perf_counter

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from src.ui.report_graph_unit_state import ReportGraphUnitState

logger = logging.getLogger(__name__)


class ReportGraphUnitController:
    """Manage minute/hour graph unit toggles and chart redraws."""

    def __init__(self, owner: object, state: ReportGraphUnitState) -> None:
        self.owner = owner
        self.state = state

    def create_unit_toggle(self) -> QWidget:
        container = QWidget(self.owner)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        minute_button = QPushButton("分", container)
        hour_button = QPushButton("時間", container)
        minute_button.setObjectName("unitMinute")
        hour_button.setObjectName("unitHour")
        for button in (minute_button, hour_button):
            button.setCheckable(True)
            button.setMinimumWidth(54)
            button.setStyleSheet(self.owner._UNIT_TOGGLE_STYLE)

        minute_button.clicked.connect(
            lambda _checked=False: self.owner._set_graph_unit(False)
        )
        hour_button.clicked.connect(
            lambda _checked=False: self.owner._set_graph_unit(True)
        )

        layout.addWidget(minute_button)
        layout.addWidget(hour_button)
        self.state.minute_buttons.append(minute_button)
        self.state.hour_buttons.append(hour_button)
        return container

    def sync_unit_controls(self) -> None:
        self.state.updating_unit_toggles = True
        try:
            for button in self.state.minute_buttons:
                button.setChecked(not self.state.graph_unit_hours)
            for button in self.state.hour_buttons:
                button.setChecked(self.state.graph_unit_hours)
        finally:
            self.state.updating_unit_toggles = False

    def set_graph_unit(self, hours: bool) -> None:
        if self.state.updating_unit_toggles:
            return
        if self.state.graph_unit_hours == hours:
            self.sync_unit_controls()
            return

        started_at = perf_counter()
        self.state.graph_unit_hours = hours
        self.sync_unit_controls()

        self.owner._set_debug_message(
            f"グラフ単位を{self.graph_unit_label()}に切替中...",
            process_events=True,
        )
        try:
            current_tab = self.owner._current_tab_index()
            tab_state = self.owner._ensure_report_tab_state()
            if current_tab == self.owner._SUMMARY_TAB:
                if tab_state.last_summary is None:
                    self.owner.refresh_summary()
                else:
                    self.owner._populate_chart(tab_state.last_summary)
                self.owner._mark_tab_clean(self.owner._SUMMARY_TAB)
                self.owner._mark_tab_dirty(self.owner._TREND_TAB)
            elif current_tab == self.owner._TREND_TAB:
                if tab_state.last_trend_series is None:
                    self.owner.refresh_trend_tab()
                else:
                    self.owner._populate_trend_chart(tab_state.last_trend_series)
                self.owner._mark_tab_clean(self.owner._TREND_TAB)
                self.owner._mark_tab_dirty(self.owner._SUMMARY_TAB)
            else:
                self.owner._mark_tab_dirty(self.owner._SUMMARY_TAB)
                self.owner._mark_tab_dirty(self.owner._TREND_TAB)
        except Exception:
            logger.exception("Failed to redraw report charts after unit toggle")
            self.owner._set_debug_message("単位切替中にエラーが発生しました")
            return

        elapsed_ms = (perf_counter() - started_at) * 1000
        self.owner._set_debug_message(
            f"グラフ単位を{self.graph_unit_label()}に切替 "
            f"({elapsed_ms:.0f} ms)"
        )

    def graph_unit_label(self) -> str:
        return "時間" if self.state.graph_unit_hours else "分"

    def seconds_to_graph_value(self, seconds: float) -> float:
        divisor = 3600.0 if self.state.graph_unit_hours else 60.0
        return seconds / divisor
