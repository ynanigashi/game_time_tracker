"""Refresh, table, operation, and chart mixins for ReportDialog."""

from __future__ import annotations

import logging
from typing import Callable, List

from src.core.reporting import ReportSummary, TrendSeries
from src.ui.report_charts import ReportChartBuilder, create_color_swatch
from src.ui.report_log_operations import ReportLogOperationController
from src.ui.report_log_operation_state import ReportLogOperationState
from src.ui.report_log_table import ReportLogTableController, bool_text
from src.ui.report_refresh import ReportRefreshController
from src.ui.report_summary_table import ReportSummaryTableController, summary_label_text
from src.ui.report_tab_refresh import ReportTabRefreshController
from src.ui.report_trend_selection import (
    ReportTrendSelectionController,
    filter_trend_series_by_indices,
    trend_selection_label,
)

logger = logging.getLogger(__name__)


class ReportDialogRefreshMixin:
    """Delegate refresh, table, log operation, and chart behavior."""

    def _get_tab_refresh_controller(self) -> ReportTabRefreshController:
        controller = getattr(self, "_tab_refresh_controller", None)
        if controller is None:
            controller = ReportTabRefreshController(
                self,
                self._ensure_report_tab_state(),
                summary_tab=self._SUMMARY_TAB,
                trend_tab=self._TREND_TAB,
                log_tab=self._LOG_TAB,
            )
            self._tab_refresh_controller = controller
        return controller

    def refresh(self, *_args: object) -> None:
        """Mark every report tab dirty and refresh only the visible tab."""
        self._get_tab_refresh_controller().refresh(force=True)

    def _current_tab_index(self) -> int:
        return self._get_tab_refresh_controller().current_tab_index()

    def _mark_tab_dirty(self, tab_index: int) -> None:
        self._get_tab_refresh_controller().mark_tab_dirty(tab_index)

    def _mark_tab_clean(self, tab_index: int) -> None:
        self._get_tab_refresh_controller().mark_tab_clean(tab_index)

    def _mark_all_tabs_dirty(self) -> None:
        self._get_tab_refresh_controller().mark_all_tabs_dirty()

    def _mark_report_data_changed(self) -> None:
        self._get_tab_refresh_controller().mark_report_data_changed()

    def _ensure_refresh_state(self) -> None:
        self._get_tab_refresh_controller().ensure_refresh_state()

    def _refresh_current_tab(self, *, force: bool = False) -> None:
        self._get_tab_refresh_controller().refresh_current_tab(force=force)

    def _refresh_tab(self, tab_index: int, *, force: bool = False) -> None:
        self._get_tab_refresh_controller().refresh_tab(tab_index, force=force)

    def _on_tab_changed(self, tab_index: int) -> None:
        self._get_tab_refresh_controller().on_tab_changed(tab_index)

    def _request_summary_refresh(self, *_args: object) -> None:
        self._mark_tab_dirty(self._SUMMARY_TAB)
        if self._current_tab_index() == self._SUMMARY_TAB:
            self._refresh_tab(self._SUMMARY_TAB, force=True)

    def _request_trend_refresh(self, *_args: object) -> None:
        self._mark_tab_dirty(self._TREND_TAB)
        if self._current_tab_index() == self._TREND_TAB:
            self._refresh_tab(self._TREND_TAB, force=True)

    def refresh_trend_tab(self, *_args: object) -> None:
        """Refresh trend controls and chart when the trend tab is visible."""
        tab_state = self._ensure_report_tab_state()
        if tab_state.title_filter_dirty or not self._title_filter_initialized:
            try:
                self._sync_title_filter(self._load_title_filter_summary())
                tab_state.title_filter_dirty = False
            except Exception:
                logger.exception("Failed to load title filter")
        self.refresh_trend()

    def _get_refresh_controller(self) -> ReportRefreshController:
        controller = getattr(self, "_refresh_controller", None)
        if controller is None:
            controller = ReportRefreshController(self)
            self._refresh_controller = controller
        return controller

    def _sync_from_spreadsheet(self, *_args: object) -> None:
        self._get_refresh_controller().sync_from_spreadsheet()

    def _sync_result_message(self, result: object) -> str:
        return self._get_refresh_controller().sync_result_message(result)

    def refresh_summary(self, *_args: object) -> None:
        """Refresh the game summary table and chart."""
        self._get_refresh_controller().refresh_summary()

    def refresh_trend(self, *_args: object) -> None:
        """Refresh the trend table and line chart."""
        self._get_refresh_controller().refresh_trend()

    def refresh_logs(self, *_args: object) -> None:
        """Refresh the raw play-log table."""
        self._get_refresh_controller().refresh_logs()

    def _get_summary_table_controller(self) -> ReportSummaryTableController:
        controller = getattr(self, "_summary_table_controller", None)
        if controller is None:
            controller = ReportSummaryTableController(
                self,
                color_swatch_factory=lambda title: create_color_swatch(
                    self.table,
                    title,
                ),
            )
            self._summary_table_controller = controller
        return controller

    def _summary_label_text(self, summary: ReportSummary) -> str:
        return summary_label_text(summary)

    def _populate_summary(self, summary: ReportSummary) -> None:
        self._get_summary_table_controller().populate_summary(summary)

    def _populate_table(self, summary: ReportSummary) -> None:
        self._get_summary_table_controller().populate_table(summary)

    def _get_trend_selection_controller(self) -> ReportTrendSelectionController:
        controller = getattr(self, "_trend_selection_controller", None)
        if controller is None:
            controller = ReportTrendSelectionController(
                self,
                self._ensure_trend_selection_state(),
                self._ensure_report_tab_state(),
                trend_series_label=self._trend_series_label,
                set_debug_message=self._set_debug_message,
            )
            self._trend_selection_controller = controller
        return controller

    def _populate_trend_table(self, series_list: List[TrendSeries]) -> None:
        self._get_trend_selection_controller().populate_trend_table(series_list)

    @staticmethod
    def _filter_trend_series_by_indices(
        series_list: List[TrendSeries],
        start_index: int,
        end_index: int,
    ) -> List[TrendSeries]:
        return filter_trend_series_by_indices(series_list, start_index, end_index)

    def _trend_selection_label(self, series_list: List[TrendSeries]) -> str:
        return trend_selection_label(series_list)

    def _populate_trend_selection(self, series_list: List[TrendSeries]) -> None:
        self._get_trend_selection_controller().populate_trend_selection(series_list)

    def _select_trend_range_from_chart(self, start_x: float, end_x: float) -> None:
        self._get_trend_selection_controller().select_trend_range_from_chart(
            start_x,
            end_x,
        )

    def _clear_trend_selection(self, *_args: object) -> None:
        self._get_trend_selection_controller().clear_trend_selection(*_args)

    def _reset_trend_chart_zoom(self) -> None:
        self._get_trend_selection_controller().reset_trend_chart_zoom()

    def _update_trend_selection_action_states(self) -> None:
        self._get_trend_selection_controller().update_action_states()

    def _get_log_table_controller(self) -> ReportLogTableController:
        controller = getattr(self, "_log_table_controller", None)
        if controller is None:
            controller = ReportLogTableController(self)
            self._log_table_controller = controller
        return controller

    def _populate_log_table(self, records: List[dict]) -> None:
        self._get_log_table_controller().populate_log_table(records)

    @staticmethod
    def _bool_text(value: object) -> str:
        return bool_text(value)

    def _selected_log_row(self) -> int:
        return self._get_log_table_controller().selected_log_row()

    def _log_table_text(self, row: int, column: int) -> str:
        return self._get_log_table_controller().log_table_text(row, column)

    def _apply_selected_log_row(self) -> None:
        self._get_log_table_controller().apply_selected_log_row()

    def _edit_selected_log_record(self, *_args: object) -> None:
        self._get_log_operation_controller().edit_selected_log_record(*_args)

    def _delete_selected_log_record(self, *_args: object) -> None:
        self._get_log_operation_controller().delete_selected_log_record(*_args)

    def _confirm_delete_log_record(self, row: int) -> bool:
        return self._get_log_operation_controller().confirm_delete_log_record(row)

    def _get_log_operation_controller(self) -> ReportLogOperationController:
        controller = getattr(self, "_log_operation_controller", None)
        if controller is None:
            controller = ReportLogOperationController(
                self,
                self._ensure_log_operation_state(),
                log_tab=self._LOG_TAB,
                set_debug_message=self._set_debug_message,
                mark_report_data_changed=self._mark_report_data_changed,
                mark_tab_clean=self._mark_tab_clean,
            )
            self._log_operation_controller = controller
        return controller

    def _ensure_log_operation_state(self) -> ReportLogOperationState:
        state = getattr(self, "_log_operation_state", None)
        if state is None:
            state = ReportLogOperationState()
            self._log_operation_state = state
        return state

    def _start_log_edit(self, record_id: str, values: List[object]) -> None:
        self._get_log_operation_controller().start_log_edit(record_id, values)

    def _start_log_delete(self, record_id: str) -> None:
        self._get_log_operation_controller().start_log_delete(record_id)

    def _start_log_operation(
        self,
        *,
        busy_message: str,
        worker: Callable[[], object],
        finish_callback: Callable[[object], None],
    ) -> None:
        self._get_log_operation_controller().start_log_operation(
            busy_message=busy_message,
            worker=worker,
            finish_callback=finish_callback,
        )

    def _check_log_edit_result(self) -> None:
        self._get_log_operation_controller().check_log_edit_result()

    def _finish_log_edit(self, result: object) -> None:
        self._get_log_operation_controller().finish_log_edit(result)

    def _finish_log_delete(self, result: object) -> None:
        self._get_log_operation_controller().finish_log_delete(result)

    def closeEvent(self, event: object) -> None:
        self._get_log_operation_controller().close()
        close_event = getattr(super(), "closeEvent", None)
        if callable(close_event):
            close_event(event)

    def _get_chart_builder(self) -> ReportChartBuilder:
        builder = getattr(self, "_chart_builder", None)
        if builder is None:
            builder = ReportChartBuilder(
                self._seconds_to_graph_value,
                self._graph_unit_label,
            )
            self._chart_builder = builder
        return builder

    def _populate_chart(self, summary: ReportSummary) -> None:
        chart_type = self.chart_type_combo.currentData()
        self._get_chart_builder().populate_summary_chart(
            self.chart_view,
            summary,
            chart_type,
        )

    def _populate_trend_chart(self, series_list: List[TrendSeries]) -> None:
        self._get_chart_builder().populate_trend_chart(
            self.trend_chart_view,
            series_list,
        )
