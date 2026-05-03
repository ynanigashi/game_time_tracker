"""Trend selection helpers for the report dialog."""

from __future__ import annotations

from typing import List

from PySide6.QtWidgets import QTableWidgetItem

from src.core.reporting import TrendSeries
from src.core.time_utils import format_hms
from src.ui.report_trend_selection_state import ReportTrendSelectionState


def filter_trend_series_by_indices(
    series_list: List[TrendSeries],
    start_index: int,
    end_index: int,
) -> List[TrendSeries]:
    if not series_list:
        return []
    lower = max(0, min(start_index, end_index))
    upper = min(max(start_index, end_index), len(series_list[0].points) - 1)
    if lower > upper:
        return []

    filtered: List[TrendSeries] = []
    for series in series_list:
        points = series.points[lower : upper + 1]
        if points:
            filtered.append(TrendSeries(title=series.title, points=points))
    return filtered


def trend_selection_label(series_list: List[TrendSeries]) -> str:
    if not series_list:
        return ""
    first_point = series_list[0].points[0]
    last_point = series_list[0].points[-1]
    return f"{first_point.start_date:%Y/%m/%d} - {last_point.end_date:%Y/%m/%d}"


class ReportTrendSelectionController:
    """Manage trend table range selection and chart zoom reset."""

    def __init__(self, owner: object, state: ReportTrendSelectionState) -> None:
        self.owner = owner
        self.state = state

    def populate_trend_table(self, series_list: List[TrendSeries]) -> None:
        rows = [
            (series.title, point)
            for series in series_list
            for point in series.points
        ]
        self.owner.trend_table.setRowCount(len(rows))
        for row_index, (title, point) in enumerate(rows):
            values = [
                title,
                point.label,
                format_hms(point.total_seconds),
                f"{point.start_date:%Y/%m/%d} - {point.end_date:%Y/%m/%d}",
            ]
            for column, value in enumerate(values):
                self.owner.trend_table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(value),
                )

    def populate_trend_selection(self, series_list: List[TrendSeries]) -> None:
        display_series = series_list
        selection_label = ""
        if self.state.selected_indices is not None:
            start_index, end_index = self.state.selected_indices
            display_series = filter_trend_series_by_indices(
                series_list,
                start_index,
                end_index,
            )
            selection_label = trend_selection_label(display_series)

        total_seconds = sum(
            point.total_seconds
            for series in display_series
            for point in series.points
        )
        period_count = len(display_series[0].points) if display_series else 0
        prefix = f"選択範囲 {selection_label} / " if selection_label else ""
        self.owner.trend_summary_label.setText(
            f"{prefix}合計 {format_hms(total_seconds)} / "
            f"{period_count} 期間 / {len(display_series)} {self.owner._trend_series_label()}"
        )
        self.populate_trend_table(display_series)

    def select_trend_range_from_chart(self, start_x: float, end_x: float) -> None:
        series_list = self.owner._ensure_report_tab_state().last_trend_series
        if self.owner.trend_chart_view is None or series_list is None:
            return
        if not series_list or not series_list[0].points:
            return

        chart = self.owner.trend_chart_view.chart()
        plot_area = chart.plotArea()
        left = float(plot_area.left())
        right = float(plot_area.right())
        width = max(1.0, right - left)
        point_count = len(series_list[0].points)
        if point_count <= 1:
            return

        def index_for_x(value: float) -> int:
            clamped = max(left, min(right, value))
            ratio = (clamped - left) / width
            return max(0, min(point_count - 1, round(ratio * (point_count - 1))))

        start_index = index_for_x(start_x)
        end_index = index_for_x(end_x)
        if start_index == end_index:
            return

        self.state.selected_indices = (
            min(start_index, end_index),
            max(start_index, end_index),
        )
        self.populate_trend_selection(series_list)
        self.update_action_states()
        self.owner._set_debug_message("推移グラフの選択範囲で集計しました")

    def clear_trend_selection(self, *_args: object) -> None:
        had_selection = self.state.selected_indices is not None
        self.state.selected_indices = None
        self.reset_trend_chart_zoom()
        self.populate_trend_selection(
            self.owner._ensure_report_tab_state().last_trend_series or []
        )
        self.update_action_states()
        if had_selection:
            self.owner._set_debug_message("推移グラフの選択範囲を解除しました")

    def reset_trend_chart_zoom(self) -> None:
        if self.owner.trend_chart_view is None:
            return
        chart = self.owner.trend_chart_view.chart()
        zoom_reset = getattr(chart, "zoomReset", None)
        if callable(zoom_reset):
            zoom_reset()

    def update_action_states(self) -> None:
        self.owner.clear_trend_selection_button.setEnabled(
            self.state.selected_indices is not None
        )
