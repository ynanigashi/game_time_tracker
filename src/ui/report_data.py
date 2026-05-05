"""Data loading helpers for the report dialog."""

from __future__ import annotations

from datetime import date
from typing import List, Optional, Tuple, TYPE_CHECKING

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit

from src.core.reporting import (
    ReportSummary,
    TrendPoint,
    TrendSeries,
    build_game_report,
    build_play_time_trend,
    build_play_time_trend_by_title,
)
from src.ui.report_date_ranges import date_range_for_period

if TYPE_CHECKING:
    from src.ui.report_dialog import ReportDialog


class ReportDataController:
    """Load summary and trend data for ReportDialog."""

    def __init__(self, owner: "ReportDialog") -> None:
        self.owner = owner

    @staticmethod
    def date_range_for_period(
        period_key: str,
        today: date,
    ) -> Tuple[Optional[date], Optional[date]]:
        return date_range_for_period(period_key, today)

    def selected_date_range(self) -> Tuple[Optional[date], Optional[date]]:
        index = self.owner.period_combo.currentIndex()
        _, period_key = self.owner._PERIODS[index]
        return self.date_range_for_period(period_key, date.today())

    def selected_trend_date_range(self) -> Tuple[Optional[date], Optional[date]]:
        period_key = str(self.owner.trend_period_combo.currentData() or "all")
        if period_key == "custom":
            return (
                self.trend_date_edit_value(self.owner.trend_start_date_edit),
                self.trend_date_edit_value(self.owner.trend_end_date_edit),
            )
        return self.date_range_for_period(period_key, date.today())

    @staticmethod
    def date_to_qdate(value: date) -> QDate:
        return QDate(value.year, value.month, value.day)

    @staticmethod
    def qdate_to_date(value: object) -> date:
        if isinstance(value, date):
            return value
        to_python = getattr(value, "toPython", None)
        if callable(to_python):
            converted = to_python()
            if isinstance(converted, date):
                return converted
        return date(int(value.year()), int(value.month()), int(value.day()))

    def trend_date_edit_value(self, date_edit: QDateEdit) -> date:
        return self.qdate_to_date(date_edit.date())

    def load_summary(self) -> ReportSummary:
        start_date, end_date = self.owner._selected_date_range()
        get_report_stats = getattr(self.owner.log_handler, "get_report_stats", None)
        if callable(get_report_stats):
            return get_report_stats(start_date=start_date, end_date=end_date)

        return build_game_report(
            self.owner._cached_records(),
            start_date=start_date,
            end_date=end_date,
        )

    def cached_records(self) -> List[dict]:
        get_cached_records = getattr(self.owner.log_handler, "get_cached_records", None)
        records = get_cached_records() if callable(get_cached_records) else []
        return list(records)

    def selected_trend_granularity(self) -> str:
        granularity = self.owner.trend_granularity_combo.currentData()
        return str(granularity or "week")

    def selected_trend_mode(self) -> str:
        mode = self.owner.trend_mode_combo.currentData()
        return str(mode or "total")

    def is_title_trend_mode(self) -> bool:
        return self.owner._selected_trend_mode() == "by_title"

    def trend_series_label(self) -> str:
        return "タイトル" if self.owner._is_title_trend_mode() else "系列"

    @staticmethod
    def total_points_to_series(points: List[TrendPoint]) -> List[TrendSeries]:
        if not points:
            return []
        return [TrendSeries(title="合計", points=points)]

    def load_total_trend_series(self) -> List[TrendSeries]:
        granularity = self.owner._selected_trend_granularity()
        start_date, end_date = self.owner._selected_trend_date_range()
        get_trend_stats = getattr(self.owner.log_handler, "get_trend_stats", None)
        if callable(get_trend_stats):
            points = get_trend_stats(
                granularity=granularity,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            points = build_play_time_trend(
                self.owner._cached_records(),
                granularity=granularity,
                start_date=start_date,
                end_date=end_date,
            )
        return self.total_points_to_series(points)

    def load_trend_series(self) -> List[TrendSeries]:
        if not self.owner._is_title_trend_mode():
            return self.owner._load_total_trend_series()

        granularity = self.owner._selected_trend_granularity()
        start_date, end_date = self.owner._selected_trend_date_range()
        titles = self.owner._selected_titles()
        get_trend_stats_by_title = getattr(
            self.owner.log_handler,
            "get_trend_stats_by_title",
            None,
        )
        if callable(get_trend_stats_by_title):
            return get_trend_stats_by_title(
                granularity=granularity,
                titles=titles,
                start_date=start_date,
                end_date=end_date,
            )

        return build_play_time_trend_by_title(
            self.owner._cached_records(),
            granularity=granularity,
            titles=titles,
            start_date=start_date,
            end_date=end_date,
        )
