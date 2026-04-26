"""Report dialog for cached play logs."""

from __future__ import annotations

import logging
from hashlib import sha1
from datetime import date, timedelta
from time import perf_counter
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.reporting import (
    ReportSummary,
    TrendPoint,
    TrendSeries,
    build_game_report,
    build_play_time_trend,
    build_play_time_trend_by_title,
)
from src.core.time_utils import format_hms

logger = logging.getLogger(__name__)

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
except Exception:
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


class ReportDialog(QDialog):
    """A non-modal report window backed by cached log records."""

    _PERIODS: Tuple[Tuple[str, str], ...] = (
        ("今日", "today"),
        ("今週", "this_week"),
        ("今月", "this_month"),
        ("今四半期", "this_quarter"),
        ("今半期", "this_half"),
        ("今年", "this_year"),
        ("直近7日", "last_7_days"),
        ("直近30日", "last_30_days"),
        ("直近60日", "last_60_days"),
        ("直近120日", "last_120_days"),
        ("直近180日", "last_180_days"),
        ("直近1年", "last_365_days"),
        ("すべて", "all"),
    )
    _RECENT_PERIOD_DAYS = {
        "last_7_days": 7,
        "last_30_days": 30,
        "last_60_days": 60,
        "last_120_days": 120,
        "last_180_days": 180,
        "last_365_days": 365,
    }
    _TREND_GRANULARITIES: Tuple[Tuple[str, str], ...] = (
        ("週別", "week"),
        ("月別", "month"),
        ("四半期別", "quarter"),
        ("半期別", "half"),
        ("年別", "year"),
    )
    _TREND_MODES: Tuple[Tuple[str, str], ...] = (
        ("合計", "total"),
        ("タイトル別", "by_title"),
    )
    _GAME_COLORS: Tuple[str, ...] = (
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
    _UNIT_TOGGLE_STYLE = """
        QPushButton {
            padding: 4px 12px;
            border: 1px solid #9CA3AF;
            border-radius: 0px;
            background: #F8FAFC;
            color: #111827;
        }
        QPushButton#unitMinute {
            border-top-left-radius: 4px;
            border-bottom-left-radius: 4px;
        }
        QPushButton#unitHour {
            border-left: 0px;
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
        }
        QPushButton:checked {
            background: #2563EB;
            border-color: #1D4ED8;
            color: white;
            font-weight: 600;
        }
    """

    def __init__(self, log_handler: object, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.log_handler = log_handler
        self.setWindowTitle("プレイレポート")
        self.resize(820, 560)

        self.period_combo = QComboBox(self)
        for label, _ in self._PERIODS:
            self.period_combo.addItem(label)
        self.period_combo.setCurrentIndex(1)
        self.period_combo.currentIndexChanged.connect(self.refresh_summary)

        self.chart_type_combo = QComboBox(self)
        self.chart_type_combo.addItem("棒グラフ", "bar")
        self.chart_type_combo.addItem("パイチャート", "pie")
        self.chart_type_combo.currentIndexChanged.connect(self.refresh_summary)

        self._graph_unit_hours = False
        self._updating_unit_toggles = False
        self._last_summary: Optional[ReportSummary] = None
        self._last_trend_series: Optional[List[TrendSeries]] = None
        self._unit_minute_buttons: List[QPushButton] = []
        self._unit_hour_buttons: List[QPushButton] = []
        self.summary_unit_control = self._create_unit_toggle()
        self.trend_unit_control = self._create_unit_toggle()
        self._sync_unit_controls()

        self.summary_label = QLabel("", self)
        self.debug_label = QLabel("", self)
        self.table = self._create_table(
            ["色", "ゲーム", "合計", "回数", "平均", "最終プレイ"],
            stretch_columns=(1,),
        )

        self.trend_granularity_combo = QComboBox(self)
        for label, key in self._TREND_GRANULARITIES:
            self.trend_granularity_combo.addItem(label, key)
        self.trend_granularity_combo.currentIndexChanged.connect(self.refresh_trend)

        self.trend_mode_combo = QComboBox(self)
        for label, key in self._TREND_MODES:
            self.trend_mode_combo.addItem(label, key)
        self.trend_mode_combo.currentIndexChanged.connect(self.refresh_trend)

        self.trend_summary_label = QLabel("", self)
        self.trend_table = self._create_table(
            ["タイトル", "期間", "合計", "範囲"],
            stretch_columns=(0, 3),
        )
        self.title_filter_table = self._create_table(
            ["タイトル"],
            stretch_columns=(0,),
        )
        self.title_filter_table.setMaximumWidth(260)
        self.title_filter_table.itemChanged.connect(self._on_title_filter_changed)
        self.select_all_titles_button = QPushButton("全選択", self)
        self.select_all_titles_button.clicked.connect(
            lambda _checked=False: self._set_all_title_filters(True)
        )
        self.clear_all_titles_button = QPushButton("全解除", self)
        self.clear_all_titles_button.clicked.connect(
            lambda _checked=False: self._set_all_title_filters(False)
        )
        self.title_filter_label = QLabel("タイトル", self)
        self._updating_title_filter = False
        self._title_filter_initialized = False

        self.chart_view = None
        self.trend_chart_view = None
        self.chart_fallback_label = None
        if CHARTS_AVAILABLE and QChartView is not None:
            self.chart_view = QChartView(self)
            self.trend_chart_view = QChartView(self)
            if QPainter is not None:
                self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
                self.trend_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        else:
            self.chart_fallback_label = QLabel(
                "PySide6.QtCharts が利用できないため、表のみ表示します。",
                self,
            )
            self.chart_fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._build_layout()
        self.refresh()

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

    def _create_unit_toggle(self) -> QWidget:
        container = QWidget(self)
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
            button.setStyleSheet(self._UNIT_TOGGLE_STYLE)

        minute_button.clicked.connect(lambda _checked=False: self._set_graph_unit(False))
        hour_button.clicked.connect(lambda _checked=False: self._set_graph_unit(True))

        layout.addWidget(minute_button)
        layout.addWidget(hour_button)
        self._unit_minute_buttons.append(minute_button)
        self._unit_hour_buttons.append(hour_button)
        return container

    def _build_layout(self) -> None:
        tabs = QTabWidget(self)
        tabs.addTab(self._build_summary_tab(), "ゲーム別")
        tabs.addTab(self._build_trend_tab(), "推移")

        layout = QVBoxLayout()
        layout.addWidget(tabs)
        layout.addWidget(self.debug_label)
        self.setLayout(layout)

    def _build_summary_tab(self) -> QWidget:
        controls = QHBoxLayout()
        controls.addWidget(QLabel("期間", self))
        controls.addWidget(self.period_combo)
        controls.addSpacing(12)
        controls.addWidget(QLabel("グラフ", self))
        controls.addWidget(self.chart_type_combo)
        controls.addSpacing(12)
        controls.addWidget(QLabel("単位", self))
        controls.addWidget(self.summary_unit_control)
        controls.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.summary_label)
        if self.chart_view is not None:
            layout.addWidget(self.chart_view, 2)
        elif self.chart_fallback_label is not None:
            layout.addWidget(self.chart_fallback_label)
        layout.addWidget(self.table, 3)

        tab = QWidget(self)
        tab.setLayout(layout)
        return tab

    def _build_trend_tab(self) -> QWidget:
        controls = QHBoxLayout()
        controls.addWidget(QLabel("表示", self))
        controls.addWidget(self.trend_mode_combo)
        controls.addSpacing(12)
        controls.addWidget(QLabel("集計単位", self))
        controls.addWidget(self.trend_granularity_combo)
        controls.addSpacing(12)
        controls.addWidget(QLabel("単位", self))
        controls.addWidget(self.trend_unit_control)
        controls.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.trend_summary_label)

        title_filter_layout = QVBoxLayout()
        title_filter_layout.addWidget(self.title_filter_label)
        title_filter_actions = QHBoxLayout()
        title_filter_actions.addWidget(self.select_all_titles_button)
        title_filter_actions.addWidget(self.clear_all_titles_button)
        title_filter_layout.addLayout(title_filter_actions)
        title_filter_layout.addWidget(self.title_filter_table)

        trend_layout = QVBoxLayout()
        if self.trend_chart_view is not None:
            trend_layout.addWidget(self.trend_chart_view, 3)
        trend_layout.addWidget(self.trend_table, 2)

        content_layout = QHBoxLayout()
        content_layout.addLayout(title_filter_layout, 1)
        content_layout.addLayout(trend_layout, 4)
        layout.addLayout(content_layout)

        tab = QWidget(self)
        tab.setLayout(layout)
        return tab

    @staticmethod
    def date_range_for_period(
        period_key: str,
        today: date,
    ) -> Tuple[Optional[date], Optional[date]]:
        """Return inclusive start/end dates for a report period key."""
        if period_key == "all":
            return None, None
        if period_key == "today":
            return today, today
        if period_key == "this_week":
            return today - timedelta(days=today.weekday()), today
        if period_key == "this_month":
            return today.replace(day=1), today
        if period_key == "this_quarter":
            quarter_start_month = ((today.month - 1) // 3) * 3 + 1
            return date(today.year, quarter_start_month, 1), today
        if period_key == "this_half":
            half_start_month = 1 if today.month <= 6 else 7
            return date(today.year, half_start_month, 1), today
        if period_key == "this_year":
            return date(today.year, 1, 1), today
        if period_key in ReportDialog._RECENT_PERIOD_DAYS:
            days = ReportDialog._RECENT_PERIOD_DAYS[period_key]
            return today - timedelta(days=days - 1), today

        logger.warning("Unknown report period: %s", period_key)
        return None, None

    def _selected_date_range(self) -> Tuple[Optional[date], Optional[date]]:
        index = self.period_combo.currentIndex()
        _, period_key = self._PERIODS[index]
        return self.date_range_for_period(period_key, date.today())

    def _load_summary(self) -> ReportSummary:
        start_date, end_date = self._selected_date_range()
        get_report_stats = getattr(self.log_handler, "get_report_stats", None)
        if callable(get_report_stats):
            return get_report_stats(start_date=start_date, end_date=end_date)

        return build_game_report(
            self._cached_records(),
            start_date=start_date,
            end_date=end_date,
        )

    def _cached_records(self) -> List[dict]:
        get_cached_records = getattr(self.log_handler, "get_cached_records", None)
        records = get_cached_records() if callable(get_cached_records) else []
        return list(records)

    def _selected_trend_granularity(self) -> str:
        granularity = self.trend_granularity_combo.currentData()
        return str(granularity or "week")

    def _selected_trend_mode(self) -> str:
        mode = self.trend_mode_combo.currentData()
        return str(mode or "total")

    def _is_title_trend_mode(self) -> bool:
        return self._selected_trend_mode() == "by_title"

    def _trend_series_label(self) -> str:
        return "タイトル" if self._is_title_trend_mode() else "系列"

    def _selected_titles(self) -> List[str]:
        titles: List[str] = []
        for row in range(self.title_filter_table.rowCount()):
            item = self.title_filter_table.item(row, 0)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                titles.append(item.text())
        return titles

    def _load_title_filter_summary(self) -> ReportSummary:
        get_report_stats = getattr(self.log_handler, "get_report_stats", None)
        if callable(get_report_stats):
            return get_report_stats(start_date=None, end_date=None)
        return build_game_report(self._cached_records())

    def _sync_title_filter(self, summary: ReportSummary) -> None:
        checked_titles = (
            set(self._selected_titles())
            if self._title_filter_initialized
            else {row.game_title for row in summary.rows}
        )
        self._updating_title_filter = True
        self.title_filter_table.blockSignals(True)
        try:
            self.title_filter_table.setRowCount(len(summary.rows))
            for row_index, row in enumerate(summary.rows):
                item = QTableWidgetItem(row.game_title)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if row.game_title in checked_titles
                    else Qt.CheckState.Unchecked
                )
                self.title_filter_table.setItem(row_index, 0, item)
        finally:
            self.title_filter_table.blockSignals(False)
            self._updating_title_filter = False
            self._title_filter_initialized = True
            self._update_title_filter_action_states()

    def _on_title_filter_changed(self, *_args: object) -> None:
        if self._updating_title_filter:
            return
        if not self._is_title_trend_mode():
            self._update_title_filter_action_states()
            return
        self.refresh_trend()
        self._update_title_filter_action_states()

    def _title_filter_counts(self) -> Tuple[int, int]:
        total_count = self.title_filter_table.rowCount()
        checked_count = 0
        for row in range(total_count):
            item = self.title_filter_table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                checked_count += 1
        return total_count, checked_count

    def _update_title_filter_action_states(self) -> None:
        title_mode = self._is_title_trend_mode()
        self.title_filter_label.setEnabled(title_mode)
        self.title_filter_table.setEnabled(title_mode)
        total_count, checked_count = self._title_filter_counts()
        self.select_all_titles_button.setEnabled(
            title_mode and total_count > 0 and checked_count < total_count
        )
        self.clear_all_titles_button.setEnabled(title_mode and checked_count > 0)

    def _set_all_title_filters(self, checked: bool) -> None:
        started_at = perf_counter()
        if not self._is_title_trend_mode():
            self._set_debug_message("合計表示ではタイトル選択は使用しません")
            self._update_title_filter_action_states()
            return
        total_count, checked_count = self._title_filter_counts()
        if total_count == 0:
            self._set_debug_message("タイトルがありません")
            self._update_title_filter_action_states()
            return
        if checked and checked_count == total_count:
            self._set_debug_message("タイトルはすでに全選択済みです")
            self._update_title_filter_action_states()
            return
        if not checked and checked_count == 0:
            self._set_debug_message("タイトルはすでに全解除済みです")
            self._update_title_filter_action_states()
            return

        self._updating_title_filter = True
        self.title_filter_table.blockSignals(True)
        try:
            for row in range(self.title_filter_table.rowCount()):
                item = self.title_filter_table.item(row, 0)
                if item is not None:
                    item.setCheckState(
                        Qt.CheckState.Checked
                        if checked
                        else Qt.CheckState.Unchecked
                    )
        finally:
            self.title_filter_table.blockSignals(False)
            self._updating_title_filter = False

        self._update_title_filter_action_states()
        self.refresh_trend()
        elapsed_ms = (perf_counter() - started_at) * 1000
        action = "全選択" if checked else "全解除"
        self._set_debug_message(f"タイトルを{action} ({elapsed_ms:.0f} ms)")

    def _set_debug_message(self, message: str, *, process_events: bool = False) -> None:
        logger.debug("ReportDialog: %s", message)
        self.debug_label.setText(f"状態: {message}")
        if process_events:
            QApplication.processEvents()

    def _sync_unit_controls(self) -> None:
        self._updating_unit_toggles = True
        try:
            for button in self._unit_minute_buttons:
                button.setChecked(not self._graph_unit_hours)
            for button in self._unit_hour_buttons:
                button.setChecked(self._graph_unit_hours)
        finally:
            self._updating_unit_toggles = False

    def _set_graph_unit(self, hours: bool) -> None:
        if self._updating_unit_toggles:
            return
        if self._graph_unit_hours == hours:
            self._sync_unit_controls()
            return

        started_at = perf_counter()
        self._graph_unit_hours = hours
        self._sync_unit_controls()

        self._set_debug_message(
            f"グラフ単位を{self._graph_unit_label()}に切替中...",
            process_events=True,
        )
        try:
            if self._last_summary is None:
                self.refresh_summary()
            else:
                self._populate_chart(self._last_summary)

            if self._last_trend_series is None:
                self.refresh_trend()
            else:
                self._populate_trend_chart(self._last_trend_series)
        except Exception:
            logger.exception("Failed to redraw report charts after unit toggle")
            self._set_debug_message("単位切替中にエラーが発生しました")
            return

        elapsed_ms = (perf_counter() - started_at) * 1000
        self._set_debug_message(
            f"グラフ単位を{self._graph_unit_label()}に切替 "
            f"({elapsed_ms:.0f} ms)"
        )

    def _graph_unit_label(self) -> str:
        return "時間" if self._graph_unit_hours else "分"

    def _seconds_to_graph_value(self, seconds: float) -> float:
        divisor = 3600.0 if self._graph_unit_hours else 60.0
        return seconds / divisor

    @staticmethod
    def _total_points_to_series(points: List[TrendPoint]) -> List[TrendSeries]:
        if not points:
            return []
        return [TrendSeries(title="合計", points=points)]

    def _load_total_trend_series(self) -> List[TrendSeries]:
        granularity = self._selected_trend_granularity()
        get_trend_stats = getattr(self.log_handler, "get_trend_stats", None)
        if callable(get_trend_stats):
            points = get_trend_stats(granularity=granularity)
        else:
            points = build_play_time_trend(
                self._cached_records(),
                granularity=granularity,
            )
        return self._total_points_to_series(points)

    def _load_trend_series(self) -> List[TrendSeries]:
        if not self._is_title_trend_mode():
            return self._load_total_trend_series()

        granularity = self._selected_trend_granularity()
        titles = self._selected_titles()
        get_trend_stats_by_title = getattr(
            self.log_handler,
            "get_trend_stats_by_title",
            None,
        )
        if callable(get_trend_stats_by_title):
            return get_trend_stats_by_title(
                granularity=granularity,
                titles=titles,
            )

        return build_play_time_trend_by_title(
            self._cached_records(),
            granularity=granularity,
            titles=titles,
        )

    def refresh(self, *_args: object) -> None:
        """Refresh all report tabs."""
        self.refresh_summary()
        try:
            self._sync_title_filter(self._load_title_filter_summary())
        except Exception:
            logger.exception("Failed to load title filter")
        self.refresh_trend()

    def refresh_summary(self, *_args: object) -> None:
        """Refresh the game summary table and chart."""
        started_at = perf_counter()
        try:
            summary = self._load_summary()
        except Exception:
            logger.exception("Failed to load report stats")
            summary = ReportSummary(rows=[], total_seconds=0.0, session_count=0)
        self._last_summary = summary

        self.summary_label.setText(
            f"合計 {format_hms(summary.total_seconds)} / "
            f"{summary.session_count} 回 / {len(summary.rows)} ゲーム"
        )
        self._populate_table(summary)
        self._populate_chart(summary)
        elapsed_ms = (perf_counter() - started_at) * 1000
        self._set_debug_message(
            f"ゲーム別集計を更新: {len(summary.rows)} タイトル "
            f"({elapsed_ms:.0f} ms)"
        )

    def refresh_trend(self, *_args: object) -> None:
        """Refresh the trend table and line chart."""
        started_at = perf_counter()
        try:
            series_list = self._load_trend_series()
        except Exception:
            logger.exception("Failed to load trend stats")
            series_list = []
        self._last_trend_series = series_list

        total_seconds = sum(
            point.total_seconds
            for series in series_list
            for point in series.points
        )
        period_count = len(series_list[0].points) if series_list else 0
        self.trend_summary_label.setText(
            f"合計 {format_hms(total_seconds)} / "
            f"{period_count} 期間 / {len(series_list)} {self._trend_series_label()}"
        )
        self._populate_trend_table(series_list)
        self._populate_trend_chart(series_list)
        self._update_title_filter_action_states()
        point_count = sum(len(series.points) for series in series_list)
        elapsed_ms = (perf_counter() - started_at) * 1000
        self._set_debug_message(
            f"推移グラフを更新: {len(series_list)} {self._trend_series_label()} / "
            f"{point_count} 点 ({elapsed_ms:.0f} ms)"
        )

    def _populate_table(self, summary: ReportSummary) -> None:
        self.table.setRowCount(len(summary.rows))
        for row_index, row in enumerate(summary.rows):
            last_played = (
                row.last_played.strftime("%Y/%m/%d %H:%M")
                if row.last_played is not None
                else "-"
            )
            self.table.setItem(row_index, 0, QTableWidgetItem(""))
            self.table.setCellWidget(
                row_index,
                0,
                self._create_color_swatch(row.game_title),
            )

            values = [
                row.game_title,
                format_hms(row.total_seconds),
                str(row.session_count),
                format_hms(row.average_seconds),
                last_played,
            ]
            for column, value in enumerate(values):
                self.table.setItem(row_index, column + 1, QTableWidgetItem(value))

    def _populate_trend_table(self, series_list: List[TrendSeries]) -> None:
        rows = [
            (series.title, point)
            for series in series_list
            for point in series.points
        ]
        self.trend_table.setRowCount(len(rows))
        for row_index, (title, point) in enumerate(rows):
            values = [
                title,
                point.label,
                format_hms(point.total_seconds),
                f"{point.start_date:%Y/%m/%d} - {point.end_date:%Y/%m/%d}",
            ]
            for column, value in enumerate(values):
                self.trend_table.setItem(row_index, column, QTableWidgetItem(value))

    def _populate_chart(self, summary: ReportSummary) -> None:
        if self.chart_view is None or not CHARTS_AVAILABLE:
            return
        if not summary.rows:
            self.chart_view.setChart(QChart())
            return

        chart_type = self.chart_type_combo.currentData()
        if chart_type == "pie":
            self.chart_view.setChart(self._build_pie_chart(summary))
            return

        self.chart_view.setChart(self._build_bar_chart(summary))

    @staticmethod
    def _top_rows_with_other(
        summary: ReportSummary,
        limit: int = 10,
    ) -> Tuple[list, float]:
        top_rows = summary.rows[:limit]
        other_seconds = sum(row.total_seconds for row in summary.rows[limit:])
        return top_rows, other_seconds

    @classmethod
    def _color_for_title(cls, title: str) -> object:
        digest = sha1(title.encode("utf-8")).digest()
        color_index = int.from_bytes(digest[:2], "big") % len(cls._GAME_COLORS)
        if QColor is None:
            return cls._GAME_COLORS[color_index]
        return QColor(cls._GAME_COLORS[color_index])

    @classmethod
    def _color_name_for_title(cls, title: str) -> str:
        color = cls._color_for_title(title)
        if hasattr(color, "name"):
            return str(color.name())
        return str(color)

    def _create_color_swatch(self, title: str) -> QWidget:
        container = QWidget(self.table)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(10, 4, 10, 4)

        swatch = QWidget(container)
        swatch.setFixedSize(28, 14)
        swatch.setStyleSheet(
            "QWidget {"
            f"background-color: {self._color_name_for_title(title)};"
            "border: 1px solid rgba(0, 0, 0, 70);"
            "border-radius: 3px;"
            "}"
        )
        layout.addWidget(swatch)
        layout.addStretch()
        return container

    def _build_bar_chart(self, summary: ReportSummary) -> object:
        top_rows = summary.rows[:10]
        values = [self._seconds_to_graph_value(row.total_seconds) for row in top_rows]
        categories = [row.game_title for row in top_rows]

        series = QStackedBarSeries()
        for row_index, row in enumerate(top_rows):
            bar_set = QBarSet(row.game_title)
            bar_set.setColor(self._color_for_title(row.game_title))
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

    def _build_pie_chart(self, summary: ReportSummary) -> object:
        top_rows, other_seconds = self._top_rows_with_other(summary, limit=8)

        series = QPieSeries()
        for row in top_rows:
            pie_slice = series.append(row.game_title, row.total_seconds)
            pie_slice.setColor(self._color_for_title(row.game_title))
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

    def _populate_trend_chart(self, series_list: List[TrendSeries]) -> None:
        if self.trend_chart_view is None or not CHARTS_AVAILABLE:
            return
        if not series_list:
            self.trend_chart_view.setChart(QChart())
            return

        self.trend_chart_view.setChart(self._build_line_chart(series_list))

    def _build_line_chart(self, series_list: List[TrendSeries]) -> object:
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
