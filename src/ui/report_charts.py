"""Chart helpers for the report dialog."""

from __future__ import annotations

from hashlib import sha1
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from src.core.reporting import ReportSummary, TrendSeries

try:
    from PySide6.QtCharts import (  # type: ignore
        QBarCategoryAxis,
        QBarSet,
        QCategoryAxis,
        QChart,
        QChartView,
        QLineSeries,
        QPieSeries,
        QStackedBarSeries,
        QValueAxis,
    )
    from PySide6.QtGui import QColor, QPainter

    CHARTS_AVAILABLE = True
    CHARTS_IMPORT_ERROR = ""
except Exception as exc:
    QBarCategoryAxis = None  # type: ignore
    QBarSet = None  # type: ignore
    QCategoryAxis = None  # type: ignore
    QChart = None  # type: ignore
    QChartView = None  # type: ignore
    QLineSeries = None  # type: ignore
    QPieSeries = None  # type: ignore
    QStackedBarSeries = None  # type: ignore
    QValueAxis = None  # type: ignore
    QColor = None  # type: ignore
    QPainter = None  # type: ignore
    CHARTS_AVAILABLE = False
    CHARTS_IMPORT_ERROR = str(exc)


GAME_COLORS: Tuple[str, ...] = (
    "#3B82F6",
    "#EF4444",
    "#10B981",
    "#F59E0B",
    "#8B5CF6",
    "#14B8A6",
    "#F97316",
    "#EC4899",
    "#6366F1",
    "#84CC16",
    "#06B6D4",
    "#A855F7",
)


if CHARTS_AVAILABLE and QChartView is not None:

    class SelectableTrendChartView(QChartView):  # type: ignore[misc]
        """Chart view that reports a horizontal drag selection in view pixels."""

        def __init__(self, on_selected: object, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._on_selected = on_selected
            self._selection_start_x: Optional[float] = None
            rubber_band = getattr(QChartView, "RubberBand", None)
            if rubber_band is not None:
                self.setRubberBand(rubber_band.HorizontalRubberBand)

        @staticmethod
        def _event_x(event: object) -> Optional[float]:
            position = None
            if hasattr(event, "position"):
                position = event.position()
            elif hasattr(event, "pos"):
                position = event.pos()
            if position is None or not hasattr(position, "x"):
                return None
            return float(position.x())

        def mousePressEvent(self, event: object) -> None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._selection_start_x = self._event_x(event)
            super().mousePressEvent(event)

        def mouseReleaseEvent(self, event: object) -> None:
            start_x = self._selection_start_x
            end_x = self._event_x(event)
            self._selection_start_x = None
            super().mouseReleaseEvent(event)
            if start_x is None or end_x is None or abs(end_x - start_x) < 8:
                return
            callback = self._on_selected
            if callable(callback):
                callback(min(start_x, end_x), max(start_x, end_x))

else:
    SelectableTrendChartView = None  # type: ignore[assignment]


def color_for_title(title: str) -> object:
    digest = sha1(title.encode("utf-8")).digest()
    color_index = int.from_bytes(digest[:2], "big") % len(GAME_COLORS)
    if QColor is None:
        return GAME_COLORS[color_index]
    return QColor(GAME_COLORS[color_index])


def color_name_for_title(title: str) -> str:
    color = color_for_title(title)
    if hasattr(color, "name"):
        return str(color.name())
    return str(color)


def top_rows_with_other(summary: ReportSummary, limit: int = 10) -> Tuple[list, float]:
    top_rows = summary.rows[:limit]
    other_seconds = sum(row.total_seconds for row in summary.rows[limit:])
    return top_rows, other_seconds


def create_color_swatch(parent: QWidget, title: str) -> QWidget:
    container = QWidget(parent)
    layout = QHBoxLayout(container)
    layout.setContentsMargins(10, 4, 10, 4)

    swatch = QWidget(container)
    swatch.setFixedSize(28, 14)
    swatch.setStyleSheet(
        "QWidget {"
        f"background-color: {color_name_for_title(title)};"
        "border: 1px solid rgba(0, 0, 0, 70);"
        "border-radius: 3px;"
        "}"
    )
    layout.addWidget(swatch)
    layout.addStretch()
    return container


def create_chart_views(parent: QWidget, on_trend_selected: object) -> tuple[object, object]:
    chart_view = QChartView(parent)
    trend_chart_view = SelectableTrendChartView(on_trend_selected, parent)
    if QPainter is not None:
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        trend_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
    return chart_view, trend_chart_view


class ReportChartBuilder:
    """Build and populate QtCharts for report summaries and trends."""

    def __init__(
        self,
        seconds_to_graph_value: Callable[[float], float],
        graph_unit_label: Callable[[], str],
    ) -> None:
        self._seconds_to_graph_value = seconds_to_graph_value
        self._graph_unit_label = graph_unit_label

    def populate_summary_chart(
        self,
        chart_view: object,
        summary: ReportSummary,
        chart_type: object,
    ) -> None:
        if chart_view is None or not CHARTS_AVAILABLE:
            return
        if not summary.rows:
            chart_view.setChart(QChart())
            return

        if chart_type == "pie":
            chart_view.setChart(self.build_pie_chart(summary))
            return

        chart_view.setChart(self.build_bar_chart(summary))

    def populate_trend_chart(
        self,
        trend_chart_view: object,
        series_list: List[TrendSeries],
    ) -> None:
        if trend_chart_view is None or not CHARTS_AVAILABLE:
            return
        if not series_list:
            trend_chart_view.setChart(QChart())
            return

        trend_chart_view.setChart(self.build_line_chart(series_list))

    def build_bar_chart(self, summary: ReportSummary) -> object:
        top_rows = summary.rows[:10]
        values = [
            self._seconds_to_graph_value(row.total_seconds)
            for row in top_rows
        ]
        categories = [row.game_title for row in top_rows]

        series = QStackedBarSeries()
        for row_index, row in enumerate(top_rows):
            bar_set = QBarSet(row.game_title)
            bar_set.setColor(color_for_title(row.game_title))
            for value_index, value in enumerate(values):
                bar_set.append(value if value_index == row_index else 0.0)
            series.append(bar_set)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("プレイ時間 上位")
        chart.legend().setVisible(False)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setTitleText(self._graph_unit_label())
        axis_y.setRange(0, max(values) * 1.15 if values else 1)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        return chart

    def build_pie_chart(self, summary: ReportSummary) -> object:
        top_rows, other_seconds = top_rows_with_other(summary, limit=8)

        series = QPieSeries()
        for row in top_rows:
            pie_slice = series.append(row.game_title, row.total_seconds)
            pie_slice.setColor(color_for_title(row.game_title))
        if other_seconds > 0:
            other_slice = series.append("その他", other_seconds)
            if QColor is not None:
                other_slice.setColor(QColor("#94A3B8"))

        for pie_slice in series.slices():
            percentage = pie_slice.percentage() * 100
            pie_slice.setLabel(f"{pie_slice.label()} {percentage:.1f}%")
            pie_slice.setLabelVisible(percentage >= 4.0)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("プレイ時間の割合")
        chart.legend().setVisible(True)
        return chart

    def build_line_chart(self, series_list: List[TrendSeries]) -> object:
        reference_points = series_list[0].points
        max_value = 0.0

        chart = QChart()
        line_series = []
        for trend_series in series_list:
            series = QLineSeries()
            series.setName(trend_series.title)
            for index, point in enumerate(trend_series.points):
                value = self._seconds_to_graph_value(point.total_seconds)
                max_value = max(max_value, value)
                series.append(float(index), value)
            chart.addSeries(series)
            line_series.append(series)

        chart.setTitle("プレイ時間の推移")
        chart.legend().setVisible(len(line_series) > 1)

        axis_x = QCategoryAxis()
        axis_x.setLabelsPosition(QCategoryAxis.AxisLabelsPositionOnValue)
        label_step = max(1, len(reference_points) // 8)
        for index, point in enumerate(reference_points):
            if index % label_step == 0 or index == len(reference_points) - 1:
                axis_x.append(point.label, float(index))
        axis_x.setRange(0.0, float(max(0, len(reference_points) - 1)))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)

        axis_y = QValueAxis()
        axis_y.setTitleText(self._graph_unit_label())
        axis_y.setRange(0, max_value * 1.15 if max_value else 1)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        for series in line_series:
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)

        return chart
