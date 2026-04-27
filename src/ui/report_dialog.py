"""Report dialog for cached play logs."""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from hashlib import sha1
from datetime import date, datetime, timedelta
from time import perf_counter
from typing import List, Optional, Tuple

from PySide6.QtCore import QDate, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
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
from src.core.time_utils import GSS_DATETIME_FORMAT
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


if CHARTS_AVAILABLE and QChartView is not None:

    class _SelectableTrendChartView(QChartView):  # type: ignore[misc]
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
    _SelectableTrendChartView = None  # type: ignore[assignment]


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
        self._log_edit_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="play-log-edit",
        )
        self._log_edit_future: Optional[Future] = None
        self._log_edit_timer: Optional[QTimer] = None
        self.setWindowTitle("プレイレポート")
        self.resize(820, 560)

        self.period_combo = QComboBox(self)
        for label, _ in self._PERIODS:
            self.period_combo.addItem(label)
        self.period_combo.setCurrentIndex(1)
        self.period_combo.currentIndexChanged.connect(self.refresh_summary)

        self.trend_period_combo = QComboBox(self)
        for label, key in self._PERIODS:
            self.trend_period_combo.addItem(label, key)
        self.trend_period_combo.addItem("日付指定", "custom")
        self.trend_period_combo.setCurrentIndex(len(self._PERIODS) - 1)
        self.trend_period_combo.currentIndexChanged.connect(
            self._on_trend_period_changed
        )
        self.trend_start_date_edit = QDateEdit(self)
        self.trend_end_date_edit = QDateEdit(self)
        for date_edit in (self.trend_start_date_edit, self.trend_end_date_edit):
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy/MM/dd")
        self.trend_apply_date_button = QPushButton("日付で絞込", self)
        self.trend_apply_date_button.clicked.connect(self._apply_custom_trend_date_range)
        self._set_trend_date_edits(date.today() - timedelta(days=29), date.today())

        self.chart_type_combo = QComboBox(self)
        self.chart_type_combo.addItem("棒グラフ", "bar")
        self.chart_type_combo.addItem("パイチャート", "pie")
        self.chart_type_combo.currentIndexChanged.connect(self.refresh_summary)

        self._graph_unit_hours = False
        self._updating_unit_toggles = False
        self._last_summary: Optional[ReportSummary] = None
        self._last_trend_series: Optional[List[TrendSeries]] = None
        self._trend_selected_indices: Optional[Tuple[int, int]] = None
        self._unit_minute_buttons: List[QPushButton] = []
        self._unit_hour_buttons: List[QPushButton] = []
        self.summary_unit_control = self._create_unit_toggle()
        self.trend_unit_control = self._create_unit_toggle()
        self._sync_unit_controls()
        self.log_sync_button = QPushButton("スプシ同期", self)
        self.log_sync_button.clicked.connect(self._sync_from_spreadsheet)
        self.log_edit_button = QPushButton("編集を保存", self)
        self.log_edit_button.clicked.connect(self._edit_selected_log_record)
        self.log_start_time_edit = QLineEdit(self)
        self.log_end_time_edit = QLineEdit(self)
        self.log_title_edit = QLineEdit(self)
        self.log_friends_check = QCheckBox(self)

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
        self.clear_trend_selection_button = QPushButton("選択解除", self)
        self.clear_trend_selection_button.clicked.connect(self._clear_trend_selection)

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
        self.log_summary_label = QLabel("", self)
        self.log_table = self._create_table(
            ["ID", "PC", "No.", "開始", "終了", "タイトル", "フレンド"],
            stretch_columns=(0, 1, 5),
        )
        self.log_table.itemSelectionChanged.connect(self._apply_selected_log_row)

        self.chart_view = None
        self.trend_chart_view = None
        self.chart_fallback_label = None
        if CHARTS_AVAILABLE and QChartView is not None:
            self.chart_view = QChartView(self)
            self.trend_chart_view = _SelectableTrendChartView(
                self._select_trend_range_from_chart,
                self,
            )
            if QPainter is not None:
                self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
                self.trend_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        else:
            self.chart_fallback_label = QLabel(
                self._chart_fallback_message(),
                self,
            )
            self.chart_fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._build_layout()
        self.refresh()

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
        tabs.addTab(self._build_log_tab(), "ログ")

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
        controls.addWidget(QLabel("期間", self))
        controls.addWidget(self.trend_period_combo)
        controls.addSpacing(12)
        controls.addWidget(QLabel("開始", self))
        controls.addWidget(self.trend_start_date_edit)
        controls.addWidget(QLabel("終了", self))
        controls.addWidget(self.trend_end_date_edit)
        controls.addWidget(self.trend_apply_date_button)
        controls.addSpacing(12)
        controls.addWidget(QLabel("表示", self))
        controls.addWidget(self.trend_mode_combo)
        controls.addSpacing(12)
        controls.addWidget(QLabel("集計単位", self))
        controls.addWidget(self.trend_granularity_combo)
        controls.addSpacing(12)
        controls.addWidget(QLabel("単位", self))
        controls.addWidget(self.trend_unit_control)
        controls.addSpacing(12)
        controls.addWidget(self.clear_trend_selection_button)
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

    def _build_log_tab(self) -> QWidget:
        controls = QHBoxLayout()
        controls.addWidget(self.log_sync_button)
        controls.addWidget(self.log_edit_button)
        controls.addStretch()

        form = QFormLayout()
        form.addRow("開始時刻", self.log_start_time_edit)
        form.addRow("終了時刻", self.log_end_time_edit)
        form.addRow("タイトル", self.log_title_edit)
        form.addRow("フレンドとプレイ", self.log_friends_check)

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.log_summary_label)
        layout.addWidget(self.log_table)
        layout.addLayout(form)

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

    def _selected_trend_date_range(self) -> Tuple[Optional[date], Optional[date]]:
        period_key = str(self.trend_period_combo.currentData() or "all")
        if period_key == "custom":
            return self._trend_date_edit_value(
                self.trend_start_date_edit
            ), self._trend_date_edit_value(self.trend_end_date_edit)
        return self.date_range_for_period(period_key, date.today())

    @staticmethod
    def _date_to_qdate(value: date) -> QDate:
        return QDate(value.year, value.month, value.day)

    @staticmethod
    def _qdate_to_date(value: object) -> date:
        if isinstance(value, date):
            return value
        to_python = getattr(value, "toPython", None)
        if callable(to_python):
            converted = to_python()
            if isinstance(converted, date):
                return converted
        return date(int(value.year()), int(value.month()), int(value.day()))

    def _trend_date_edit_value(self, date_edit: QDateEdit) -> date:
        return self._qdate_to_date(date_edit.date())

    def _set_trend_date_edits(self, start_date: date, end_date: date) -> None:
        self.trend_start_date_edit.setDate(self._date_to_qdate(start_date))
        self.trend_end_date_edit.setDate(self._date_to_qdate(end_date))

    def _on_trend_period_changed(self, *_args: object) -> None:
        period_key = str(self.trend_period_combo.currentData() or "all")
        if period_key != "custom":
            start_date, end_date = self.date_range_for_period(period_key, date.today())
            if start_date is not None and end_date is not None:
                self._set_trend_date_edits(start_date, end_date)
        self.refresh_trend()

    def _apply_custom_trend_date_range(self, *_args: object) -> None:
        start_date = self._trend_date_edit_value(self.trend_start_date_edit)
        end_date = self._trend_date_edit_value(self.trend_end_date_edit)
        if start_date > end_date:
            QMessageBox.warning(self, "期間指定エラー", "開始日は終了日以前にしてください")
            return

        custom_index = self.trend_period_combo.findData("custom")
        if custom_index >= 0:
            self.trend_period_combo.setCurrentIndex(custom_index)
        self.refresh_trend()

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
        start_date, end_date = self._selected_trend_date_range()
        get_trend_stats = getattr(self.log_handler, "get_trend_stats", None)
        if callable(get_trend_stats):
            points = get_trend_stats(
                granularity=granularity,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            points = build_play_time_trend(
                self._cached_records(),
                granularity=granularity,
                start_date=start_date,
                end_date=end_date,
            )
        return self._total_points_to_series(points)

    def _load_trend_series(self) -> List[TrendSeries]:
        if not self._is_title_trend_mode():
            return self._load_total_trend_series()

        granularity = self._selected_trend_granularity()
        start_date, end_date = self._selected_trend_date_range()
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
                start_date=start_date,
                end_date=end_date,
            )

        return build_play_time_trend_by_title(
            self._cached_records(),
            granularity=granularity,
            titles=titles,
            start_date=start_date,
            end_date=end_date,
        )

    def refresh(self, *_args: object) -> None:
        """Refresh all report tabs."""
        self.refresh_summary()
        try:
            self._sync_title_filter(self._load_title_filter_summary())
        except Exception:
            logger.exception("Failed to load title filter")
        self.refresh_trend()
        self.refresh_logs()

    def _sync_from_spreadsheet(self, *_args: object) -> None:
        sync_with_spreadsheet = getattr(
            self.log_handler,
            "sync_with_spreadsheet",
            None,
        )
        if not callable(sync_with_spreadsheet):
            self._set_debug_message("スプシ同期に対応していないログハンドラです")
            return

        self._set_debug_message("スプシ同期中...", process_events=True)
        try:
            result = sync_with_spreadsheet()
        except Exception:
            logger.exception("Failed to sync play logs from spreadsheet")
            self._set_debug_message("スプシ同期に失敗しました")
            return

        self.refresh()
        self._set_debug_message(self._sync_result_message(result))

    def _sync_result_message(self, result: object) -> str:
        error_message = str(getattr(result, "error_message", "") or "")
        parts = [
            "スプシ同期一部失敗" if error_message else "スプシ同期完了",
            f"取得 {getattr(result, 'remote_count', 0)} 件",
            f"取込 {getattr(result, 'imported', 0)} 件",
            f"取込スキップ {getattr(result, 'import_skipped', 0)} 件",
            f"未送信 {getattr(result, 'pending_count', 0)} 件",
            f"バックアップ {getattr(result, 'backed_up', 0)} 件",
        ]
        backup_failed = getattr(result, "backup_failed", 0)
        if backup_failed:
            parts.append(f"バックアップ失敗 {backup_failed} 件")
        overwritten = getattr(result, "overwritten", 0)
        if overwritten:
            parts.append(f"上書き {overwritten} 件")
        reissued = getattr(result, "reissued", 0)
        if reissued:
            parts.append(f"別ID {reissued} 件")
        parts.append(f"合計 {getattr(result, 'total', len(self._cached_records()))} 件")

        if error_message:
            parts.append(f"注意: {error_message}")
        return " / ".join(parts)

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
        self._trend_selected_indices = None
        started_at = perf_counter()
        try:
            series_list = self._load_trend_series()
        except Exception:
            logger.exception("Failed to load trend stats")
            series_list = []
        self._last_trend_series = series_list

        self._populate_trend_selection(series_list)
        self._populate_trend_chart(series_list)
        self._update_title_filter_action_states()
        self._update_trend_selection_action_states()
        point_count = sum(len(series.points) for series in series_list)
        elapsed_ms = (perf_counter() - started_at) * 1000
        self._set_debug_message(
            f"推移グラフを更新: {len(series_list)} {self._trend_series_label()} / "
            f"{point_count} 点 ({elapsed_ms:.0f} ms)"
        )

    def refresh_logs(self, *_args: object) -> None:
        """Refresh the raw play-log table."""
        records = self._cached_records()
        self.log_summary_label.setText(f"ログ {len(records)} 件")
        self._populate_log_table(records)
        self._apply_selected_log_row()

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

    @staticmethod
    def _filter_trend_series_by_indices(
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

    def _trend_selection_label(self, series_list: List[TrendSeries]) -> str:
        if not series_list:
            return ""
        first_point = series_list[0].points[0]
        last_point = series_list[0].points[-1]
        return f"{first_point.start_date:%Y/%m/%d} - {last_point.end_date:%Y/%m/%d}"

    def _populate_trend_selection(self, series_list: List[TrendSeries]) -> None:
        display_series = series_list
        selection_label = ""
        if self._trend_selected_indices is not None:
            start_index, end_index = self._trend_selected_indices
            display_series = self._filter_trend_series_by_indices(
                series_list,
                start_index,
                end_index,
            )
            selection_label = self._trend_selection_label(display_series)

        total_seconds = sum(
            point.total_seconds
            for series in display_series
            for point in series.points
        )
        period_count = len(display_series[0].points) if display_series else 0
        prefix = f"選択範囲 {selection_label} / " if selection_label else ""
        self.trend_summary_label.setText(
            f"{prefix}合計 {format_hms(total_seconds)} / "
            f"{period_count} 期間 / {len(display_series)} {self._trend_series_label()}"
        )
        self._populate_trend_table(display_series)

    def _select_trend_range_from_chart(self, start_x: float, end_x: float) -> None:
        if self.trend_chart_view is None or self._last_trend_series is None:
            return
        if not self._last_trend_series or not self._last_trend_series[0].points:
            return

        chart = self.trend_chart_view.chart()
        plot_area = chart.plotArea()
        left = float(plot_area.left())
        right = float(plot_area.right())
        width = max(1.0, right - left)
        point_count = len(self._last_trend_series[0].points)
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

        self._trend_selected_indices = (
            min(start_index, end_index),
            max(start_index, end_index),
        )
        self._populate_trend_selection(self._last_trend_series)
        self._update_trend_selection_action_states()
        self._set_debug_message("推移グラフの選択範囲で集計しました")

    def _clear_trend_selection(self, *_args: object) -> None:
        had_selection = self._trend_selected_indices is not None
        self._trend_selected_indices = None
        self._reset_trend_chart_zoom()
        self._populate_trend_selection(self._last_trend_series or [])
        self._update_trend_selection_action_states()
        if had_selection:
            self._set_debug_message("推移グラフの選択範囲を解除しました")

    def _reset_trend_chart_zoom(self) -> None:
        if self.trend_chart_view is None:
            return
        chart = self.trend_chart_view.chart()
        zoom_reset = getattr(chart, "zoomReset", None)
        if callable(zoom_reset):
            zoom_reset()

    def _update_trend_selection_action_states(self) -> None:
        self.clear_trend_selection_button.setEnabled(
            self._trend_selected_indices is not None
        )

    def _populate_log_table(self, records: List[dict]) -> None:
        rows = sorted(
            records,
            key=lambda record: int(record.get("index") or 0),
            reverse=True,
        )
        self.log_table.setRowCount(len(rows))
        for row_index, record in enumerate(rows):
            values = [
                str(record.get("record_id", "")),
                str(record.get("device_id", "")),
                str(record.get("index", "")),
                str(record.get("start_time", "")),
                str(record.get("end_time", "")),
                str(record.get("title", "")),
                self._bool_text(record.get("play_with_friends", False)),
            ]
            for column, value in enumerate(values):
                self.log_table.setItem(row_index, column, QTableWidgetItem(value))

    @staticmethod
    def _bool_text(value: object) -> str:
        return "TRUE" if value is True or str(value).upper() == "TRUE" else "FALSE"

    def _selected_log_row(self) -> int:
        row = self.log_table.currentRow()
        return row if 0 <= row < self.log_table.rowCount() else -1

    def _log_table_text(self, row: int, column: int) -> str:
        item = self.log_table.item(row, column)
        return item.text() if item is not None else ""

    def _apply_selected_log_row(self) -> None:
        row = self._selected_log_row()
        if row < 0:
            self.log_start_time_edit.setText("")
            self.log_end_time_edit.setText("")
            self.log_title_edit.setText("")
            self.log_friends_check.setChecked(False)
            return
        self.log_start_time_edit.setText(self._log_table_text(row, 3))
        self.log_end_time_edit.setText(self._log_table_text(row, 4))
        self.log_title_edit.setText(self._log_table_text(row, 5))
        self.log_friends_check.setChecked(self._log_table_text(row, 6) == "TRUE")

    def _edit_selected_log_record(self, *_args: object) -> None:
        row = self._selected_log_row()
        if row < 0:
            QMessageBox.warning(self, "ログ編集エラー", "編集するレコードを選択してください")
            return

        record_id = self._log_table_text(row, 0).strip()
        if not record_id:
            QMessageBox.warning(self, "ログ編集エラー", "レコードIDが見つかりません")
            return

        start_time = self.log_start_time_edit.text().strip()
        end_time = self.log_end_time_edit.text().strip()
        title = self.log_title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "ログ編集エラー", "タイトルを入力してください")
            return

        try:
            start = datetime.strptime(start_time, GSS_DATETIME_FORMAT)
            end = datetime.strptime(end_time, GSS_DATETIME_FORMAT)
        except ValueError:
            QMessageBox.warning(
                self,
                "ログ編集エラー",
                "日時は YYYY/MM/DD HH:MM:SS 形式で入力してください",
            )
            return
        if end <= start:
            QMessageBox.warning(self, "ログ編集エラー", "終了時刻は開始時刻より後にしてください")
            return

        update_record = getattr(self.log_handler, "update_record", None)
        if not callable(update_record):
            QMessageBox.warning(self, "ログ編集エラー", "このログハンドラは編集に対応していません")
            return

        values = [
            int(self._log_table_text(row, 2)),
            start_time,
            end_time,
            title,
            self.log_friends_check.isChecked(),
        ]
        self._start_log_edit(record_id, values)

    def _start_log_edit(self, record_id: str, values: List[object]) -> None:
        if self._log_edit_future is not None and not self._log_edit_future.done():
            self._set_debug_message("ログ編集中です。完了まで待ってください")
            return

        update_record = getattr(self.log_handler, "update_record", None)
        if not callable(update_record):
            QMessageBox.warning(self, "ログ編集エラー", "このログハンドラは編集に対応していません")
            return

        self.log_edit_button.setEnabled(False)
        self._set_debug_message("ログ編集を保存中...", process_events=True)
        self._log_edit_future = self._log_edit_executor.submit(
            update_record,
            record_id,
            values,
        )
        self._log_edit_timer = QTimer(self)
        self._log_edit_timer.setInterval(100)
        self._log_edit_timer.timeout.connect(self._check_log_edit_result)
        self._log_edit_timer.start()

    def _check_log_edit_result(self) -> None:
        future = self._log_edit_future
        if future is None or not future.done():
            return

        if self._log_edit_timer is not None:
            self._log_edit_timer.stop()
            self._log_edit_timer.deleteLater()
            self._log_edit_timer = None
        self._log_edit_future = None
        self.log_edit_button.setEnabled(True)

        try:
            result = future.result()
        except Exception as exc:
            logger.exception("Failed to edit play log")
            QMessageBox.warning(self, "ログ編集エラー", str(exc))
            return

        self._finish_log_edit(result)

    def _finish_log_edit(self, result: object) -> None:
        if not getattr(result, "local_updated", False):
            QMessageBox.warning(
                self,
                "ログ編集エラー",
                str(getattr(result, "error_message", "") or "ローカルDBの更新に失敗しました"),
            )
            return

        self.refresh()
        if getattr(result, "spreadsheet_updated", False):
            self._set_debug_message("ログを編集し、スプシにも反映しました")
            return

        error_message = str(getattr(result, "error_message", "") or "")
        if error_message:
            self._set_debug_message(f"ログを編集しました。スプシ反映は失敗しました: {error_message}")
        else:
            self._set_debug_message("ログを編集しました。スプシ設定がないためローカルのみ更新しました")

    def closeEvent(self, event: object) -> None:
        if self._log_edit_timer is not None:
            self._log_edit_timer.stop()
            self._log_edit_timer = None
        self._log_edit_executor.shutdown(wait=False, cancel_futures=True)
        close_event = getattr(super(), "closeEvent", None)
        if callable(close_event):
            close_event(event)

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
