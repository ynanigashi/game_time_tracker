"""Data and input helpers for ReportDialog."""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional, Tuple

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QDateEdit, QMessageBox

from src.core.reporting import ReportSummary, TrendPoint, TrendSeries
from src.ui.report_data import ReportDataController
from src.ui.report_date_ranges import date_range_for_period
from src.ui.report_title_filter import ReportTitleFilterController

logger = logging.getLogger(__name__)


class ReportDialogDataMixin:
    """Delegate report data loading and date inputs."""

    def _get_data_controller(self) -> ReportDataController:
        controller = getattr(self, "_data_controller", None)
        if controller is None:
            controller = ReportDataController(self)
            self._data_controller = controller
        return controller

    @staticmethod
    def date_range_for_period(
        period_key: str,
        today: date,
    ) -> Tuple[Optional[date], Optional[date]]:
        """Return inclusive start/end dates for a report period key."""
        return date_range_for_period(period_key, today)

    def _selected_date_range(self) -> Tuple[Optional[date], Optional[date]]:
        return self._get_data_controller().selected_date_range()

    def _selected_trend_date_range(self) -> Tuple[Optional[date], Optional[date]]:
        return self._get_data_controller().selected_trend_date_range()

    @staticmethod
    def _date_to_qdate(value: date) -> QDate:
        return ReportDataController.date_to_qdate(value)

    @staticmethod
    def _qdate_to_date(value: object) -> date:
        return ReportDataController.qdate_to_date(value)

    def _trend_date_edit_value(self, date_edit: QDateEdit) -> date:
        return self._get_data_controller().trend_date_edit_value(date_edit)

    def _set_trend_date_edits(self, start_date: date, end_date: date) -> None:
        self.trend_start_date_edit.setDate(self._date_to_qdate(start_date))
        self.trend_end_date_edit.setDate(self._date_to_qdate(end_date))

    def _on_trend_period_changed(self, *_args: object) -> None:
        period_key = str(self.trend_period_combo.currentData() or "all")
        if period_key != "custom":
            start_date, end_date = self.date_range_for_period(period_key, date.today())
            if start_date is not None and end_date is not None:
                self._set_trend_date_edits(start_date, end_date)
        self._request_trend_refresh()

    def _apply_custom_trend_date_range(self, *_args: object) -> None:
        start_date = self._trend_date_edit_value(self.trend_start_date_edit)
        end_date = self._trend_date_edit_value(self.trend_end_date_edit)
        if start_date > end_date:
            QMessageBox.warning(self, "期間指定エラー", "開始日は終了日以前にしてください")
            return

        custom_index = self.trend_period_combo.findData("custom")
        if custom_index >= 0:
            self.trend_period_combo.setCurrentIndex(custom_index)
        self._request_trend_refresh()

    def _load_summary(self) -> ReportSummary:
        return self._get_data_controller().load_summary()

    def _cached_records(self) -> List[dict]:
        return self._get_data_controller().cached_records()

    def _selected_trend_granularity(self) -> str:
        return self._get_data_controller().selected_trend_granularity()

    def _selected_trend_mode(self) -> str:
        return self._get_data_controller().selected_trend_mode()

    def _is_title_trend_mode(self) -> bool:
        return self._get_data_controller().is_title_trend_mode()

    def _trend_series_label(self) -> str:
        return self._get_data_controller().trend_series_label()

    def _get_title_filter_controller(self) -> ReportTitleFilterController:
        controller = getattr(self, "_title_filter_controller", None)
        if controller is None:
            controller = ReportTitleFilterController(
                self,
                self._ensure_title_filter_state(),
                self._ensure_report_tab_state(),
                trend_tab=self._TREND_TAB,
                cached_records=self._cached_records,
                is_title_trend_mode=self._is_title_trend_mode,
                refresh_trend=self.refresh_trend,
                mark_tab_clean=self._mark_tab_clean,
                set_debug_message=self._set_debug_message,
            )
            self._title_filter_controller = controller
        return controller

    def _selected_titles(self) -> List[str]:
        return self._get_title_filter_controller().selected_titles()

    def _load_title_filter_summary(self) -> ReportSummary:
        return self._get_title_filter_controller().load_title_filter_summary()

    def _sync_title_filter(self, summary: ReportSummary) -> None:
        self._get_title_filter_controller().sync_title_filter(summary)

    def _on_title_filter_changed(self, *_args: object) -> None:
        self._get_title_filter_controller().on_title_filter_changed(*_args)

    def _title_filter_counts(self) -> Tuple[int, int]:
        return self._get_title_filter_controller().title_filter_counts()

    def _update_title_filter_action_states(self) -> None:
        self._get_title_filter_controller().update_action_states()

    def _set_all_title_filters(self, checked: bool) -> None:
        self._get_title_filter_controller().set_all_title_filters(checked)

    def _set_debug_message(self, message: str, *, process_events: bool = False) -> None:
        logger.debug("ReportDialog: %s", message)
        self.debug_label.setText(f"状態: {message}")
        if process_events:
            QApplication.processEvents()

    def _sync_unit_controls(self) -> None:
        self._get_graph_unit_controller().sync_unit_controls()

    def _set_graph_unit(self, hours: bool) -> None:
        self._get_graph_unit_controller().set_graph_unit(hours)

    def _graph_unit_label(self) -> str:
        return self._get_graph_unit_controller().graph_unit_label()

    def _seconds_to_graph_value(self, seconds: float) -> float:
        return self._get_graph_unit_controller().seconds_to_graph_value(seconds)

    @staticmethod
    def _total_points_to_series(points: List[TrendPoint]) -> List[TrendSeries]:
        return ReportDataController.total_points_to_series(points)

    def _load_total_trend_series(self) -> List[TrendSeries]:
        return self._get_data_controller().load_total_trend_series()

    def _load_trend_series(self) -> List[TrendSeries]:
        return self._get_data_controller().load_trend_series()

