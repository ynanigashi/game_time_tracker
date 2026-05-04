"""State and UI helper mixins for ReportDialog."""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QWidget,
)

from src.core.reporting import ReportSummary, TrendSeries
from src.ui.report_charts import CHARTS_IMPORT_ERROR
from src.ui.report_graph_unit import ReportGraphUnitController
from src.ui.report_graph_unit_state import ReportGraphUnitState
from src.ui.report_tab_state import ReportTabState
from src.ui.report_title_filter_state import ReportTitleFilterState
from src.ui.report_trend_selection_state import ReportTrendSelectionState


class ReportDialogStateMixin:
    """Own compatibility accessors for ReportDialog state objects."""

    def _ensure_report_tab_state(self) -> ReportTabState:
        state = getattr(self, "_tab_state", None)
        if state is None:
            state = ReportTabState()
            self._tab_state = state
        return state

    @property
    def _loaded_tabs(self) -> set[int]:
        return self._ensure_report_tab_state().loaded_tabs

    @_loaded_tabs.setter
    def _loaded_tabs(self, value: set[int]) -> None:
        self._ensure_report_tab_state().loaded_tabs = set(value)

    @property
    def _dirty_tabs(self) -> set[int]:
        return self._ensure_report_tab_state().dirty_tabs

    @_dirty_tabs.setter
    def _dirty_tabs(self, value: set[int]) -> None:
        self._ensure_report_tab_state().dirty_tabs = set(value)

    @property
    def _title_filter_dirty(self) -> bool:
        return self._ensure_report_tab_state().title_filter_dirty

    @_title_filter_dirty.setter
    def _title_filter_dirty(self, value: bool) -> None:
        self._ensure_report_tab_state().title_filter_dirty = bool(value)

    @property
    def _last_summary(self) -> Optional[ReportSummary]:
        return self._ensure_report_tab_state().last_summary

    @_last_summary.setter
    def _last_summary(self, value: Optional[ReportSummary]) -> None:
        self._ensure_report_tab_state().last_summary = value

    @property
    def _title_filter_summary(self) -> Optional[ReportSummary]:
        return self._ensure_report_tab_state().title_filter_summary

    @_title_filter_summary.setter
    def _title_filter_summary(self, value: Optional[ReportSummary]) -> None:
        self._ensure_report_tab_state().title_filter_summary = value

    @property
    def _last_trend_series(self) -> Optional[List[TrendSeries]]:
        return self._ensure_report_tab_state().last_trend_series

    @_last_trend_series.setter
    def _last_trend_series(self, value: Optional[List[TrendSeries]]) -> None:
        self._ensure_report_tab_state().last_trend_series = value

    def _ensure_title_filter_state(self) -> ReportTitleFilterState:
        state = getattr(self, "_title_filter_state", None)
        if state is None:
            state = ReportTitleFilterState()
            self._title_filter_state = state
        return state

    @property
    def _updating_title_filter(self) -> bool:
        return self._ensure_title_filter_state().updating

    @_updating_title_filter.setter
    def _updating_title_filter(self, value: bool) -> None:
        self._ensure_title_filter_state().updating = bool(value)

    @property
    def _title_filter_initialized(self) -> bool:
        return self._ensure_title_filter_state().initialized

    @_title_filter_initialized.setter
    def _title_filter_initialized(self, value: bool) -> None:
        self._ensure_title_filter_state().initialized = bool(value)

    def _ensure_trend_selection_state(self) -> ReportTrendSelectionState:
        state = getattr(self, "_trend_selection_state", None)
        if state is None:
            state = ReportTrendSelectionState()
            self._trend_selection_state = state
        return state

    @property
    def _trend_selected_indices(self) -> Optional[Tuple[int, int]]:
        return self._ensure_trend_selection_state().selected_indices

    @_trend_selected_indices.setter
    def _trend_selected_indices(self, value: Optional[Tuple[int, int]]) -> None:
        if value is None:
            self._ensure_trend_selection_state().selected_indices = None
            return
        self._ensure_trend_selection_state().selected_indices = (
            int(value[0]),
            int(value[1]),
        )

    @staticmethod
    def _chart_fallback_message() -> str:
        message = "PySide6.QtCharts が利用できないため、表のみ表示します。"
        if CHARTS_IMPORT_ERROR:
            return f"{message}\n原因: {CHARTS_IMPORT_ERROR}"
        return message

    def _create_table(
        self,
        headers: List[str],
        *,
        stretch_columns: Tuple[int, ...],
    ) -> QTableWidget:
        table = QTableWidget(self)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for column in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if column in stretch_columns
                else QHeaderView.ResizeMode.ResizeToContents
            )
            table.horizontalHeader().setSectionResizeMode(column, mode)
        return table

    def _get_graph_unit_controller(self) -> ReportGraphUnitController:
        controller = getattr(self, "_graph_unit_controller", None)
        if controller is None:
            controller = ReportGraphUnitController(
                self,
                self._ensure_graph_unit_state(),
                self._ensure_report_tab_state(),
                summary_tab=self._SUMMARY_TAB,
                trend_tab=self._TREND_TAB,
                unit_toggle_style=self._UNIT_TOGGLE_STYLE,
                set_debug_message=self._set_debug_message,
                current_tab_index=self._current_tab_index,
                refresh_summary=self.refresh_summary,
                populate_chart=self._populate_chart,
                refresh_trend_tab=self.refresh_trend_tab,
                populate_trend_chart=self._populate_trend_chart,
                mark_tab_clean=self._mark_tab_clean,
                mark_tab_dirty=self._mark_tab_dirty,
            )
            self._graph_unit_controller = controller
        return controller

    def _ensure_graph_unit_state(self) -> ReportGraphUnitState:
        state = getattr(self, "_graph_unit_state", None)
        if state is None:
            state = ReportGraphUnitState()
            self._graph_unit_state = state
        return state

    @property
    def _graph_unit_hours(self) -> bool:
        return self._ensure_graph_unit_state().graph_unit_hours

    @_graph_unit_hours.setter
    def _graph_unit_hours(self, value: bool) -> None:
        self._ensure_graph_unit_state().graph_unit_hours = bool(value)

    @property
    def _updating_unit_toggles(self) -> bool:
        return self._ensure_graph_unit_state().updating_unit_toggles

    @_updating_unit_toggles.setter
    def _updating_unit_toggles(self, value: bool) -> None:
        self._ensure_graph_unit_state().updating_unit_toggles = bool(value)

    @property
    def _unit_minute_buttons(self) -> List[QPushButton]:
        return self._ensure_graph_unit_state().minute_buttons

    @_unit_minute_buttons.setter
    def _unit_minute_buttons(self, value: List[QPushButton]) -> None:
        self._ensure_graph_unit_state().minute_buttons = list(value)

    @property
    def _unit_hour_buttons(self) -> List[QPushButton]:
        return self._ensure_graph_unit_state().hour_buttons

    @_unit_hour_buttons.setter
    def _unit_hour_buttons(self, value: List[QPushButton]) -> None:
        self._ensure_graph_unit_state().hour_buttons = list(value)

    def _create_unit_toggle(self) -> QWidget:
        return self._get_graph_unit_controller().create_unit_toggle()

