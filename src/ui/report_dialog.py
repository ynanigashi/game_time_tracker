"""Report dialog for cached play logs."""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime, timedelta
from time import perf_counter
from typing import Callable, List, Optional, Tuple

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
from src.ui.report_charts import (
    CHARTS_AVAILABLE,
    CHARTS_IMPORT_ERROR,
    GAME_COLORS,
    ReportChartBuilder,
    color_for_title,
    color_name_for_title,
    create_chart_views,
    create_color_swatch,
    top_rows_with_other,
)
from src.ui.report_date_ranges import RECENT_PERIOD_DAYS, date_range_for_period
from src.ui.report_graph_unit import ReportGraphUnitController
from src.ui.report_log_operations import ReportLogOperationController
from src.ui.report_log_table import ReportLogTableController, bool_text
from src.ui.report_summary_table import (
    ReportSummaryTableController,
    summary_label_text,
)
from src.ui.report_sync_messages import sync_result_message
from src.ui.report_tab_refresh import ReportTabRefreshController
from src.ui.report_tab_state import ReportTabState
from src.ui.report_title_filter import ReportTitleFilterController
from src.ui.report_trend_selection import (
    ReportTrendSelectionController,
    filter_trend_series_by_indices,
    trend_selection_label,
)

logger = logging.getLogger(__name__)


class ReportDialog(QDialog):
    """A non-modal report window backed by cached log records."""

    _SUMMARY_TAB = 0
    _TREND_TAB = 1
    _LOG_TAB = 2

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
    _RECENT_PERIOD_DAYS = RECENT_PERIOD_DAYS
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
    _GAME_COLORS = GAME_COLORS
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
        self._tab_state = ReportTabState(
            dirty_tabs={
                self._SUMMARY_TAB,
                self._TREND_TAB,
                self._LOG_TAB,
            }
        )
        self._log_edit_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="play-log-edit",
        )
        self._log_edit_future: Optional[Future] = None
        self._log_edit_timer: Optional[QTimer] = None
        self._log_edit_finish_callback: Optional[Callable[[object], None]] = None
        self.setWindowTitle("プレイレポート")
        self.resize(820, 560)

        self.period_combo = QComboBox(self)
        for label, _ in self._PERIODS:
            self.period_combo.addItem(label)
        self.period_combo.setCurrentIndex(1)
        self.period_combo.currentIndexChanged.connect(self._request_summary_refresh)

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
        self.chart_type_combo.currentIndexChanged.connect(self._request_summary_refresh)

        self._graph_unit_hours = False
        self._updating_unit_toggles = False
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
        self.log_delete_button = QPushButton("削除", self)
        self.log_delete_button.clicked.connect(self._delete_selected_log_record)
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
        self.trend_granularity_combo.currentIndexChanged.connect(
            self._request_trend_refresh
        )

        self.trend_mode_combo = QComboBox(self)
        for label, key in self._TREND_MODES:
            self.trend_mode_combo.addItem(label, key)
        self.trend_mode_combo.currentIndexChanged.connect(self._request_trend_refresh)
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
        if CHARTS_AVAILABLE:
            self.chart_view, self.trend_chart_view = create_chart_views(
                self,
                self._select_trend_range_from_chart,
            )
        else:
            self.chart_fallback_label = QLabel(
                self._chart_fallback_message(),
                self,
            )
            self.chart_fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._build_layout()
        self.refresh()

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
            controller = ReportGraphUnitController(self)
            self._graph_unit_controller = controller
        return controller

    def _create_unit_toggle(self) -> QWidget:
        return self._get_graph_unit_controller().create_unit_toggle()

    def _build_layout(self) -> None:
        tabs = QTabWidget(self)
        tabs.addTab(self._build_summary_tab(), "ゲーム別")
        tabs.addTab(self._build_trend_tab(), "推移")
        tabs.addTab(self._build_log_tab(), "ログ")
        tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs = tabs

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
        controls.addWidget(self.log_delete_button)
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
        return date_range_for_period(period_key, today)

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

    def _get_title_filter_controller(self) -> ReportTitleFilterController:
        controller = getattr(self, "_title_filter_controller", None)
        if controller is None:
            controller = ReportTitleFilterController(self)
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

    def _get_tab_refresh_controller(self) -> ReportTabRefreshController:
        controller = getattr(self, "_tab_refresh_controller", None)
        if controller is None:
            controller = ReportTabRefreshController(self)
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
        return sync_result_message(result, lambda: len(self._cached_records()))

    def refresh_summary(self, *_args: object) -> None:
        """Refresh the game summary table and chart."""
        started_at = perf_counter()
        try:
            summary = self._load_summary()
        except Exception:
            logger.exception("Failed to load report stats")
            summary = ReportSummary(rows=[], total_seconds=0.0, session_count=0)
        self._ensure_report_tab_state().last_summary = summary

        self._populate_summary(summary)
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
        self._ensure_report_tab_state().last_trend_series = series_list

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
            controller = ReportTrendSelectionController(self)
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

    def _delete_selected_log_record(self, *_args: object) -> None:
        row = self._selected_log_row()
        if row < 0:
            QMessageBox.warning(self, "ログ削除エラー", "削除するレコードを選択してください")
            return

        record_id = self._log_table_text(row, 0).strip()
        if not record_id:
            QMessageBox.warning(self, "ログ削除エラー", "レコードIDが見つかりません")
            return

        if not self._confirm_delete_log_record(row):
            return

        self._start_log_delete(record_id)

    def _confirm_delete_log_record(self, row: int) -> bool:
        question = getattr(QMessageBox, "question", None)
        standard_button = getattr(QMessageBox, "StandardButton", None)
        yes = getattr(standard_button, "Yes", None)
        no = getattr(standard_button, "No", None)
        if not callable(question) or yes is None or no is None:
            return True

        title = self._log_table_text(row, 5)
        start_time = self._log_table_text(row, 3)
        selected = question(
            self,
            "ログ削除",
            f"このログを削除しますか？\n{start_time} / {title}",
            yes | no,
            no,
        )
        return selected == yes

    def _get_log_operation_controller(self) -> ReportLogOperationController:
        controller = getattr(self, "_log_operation_controller", None)
        if controller is None:
            controller = ReportLogOperationController(self)
            self._log_operation_controller = controller
        return controller

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

    @staticmethod
    def _top_rows_with_other(
        summary: ReportSummary,
        limit: int = 10,
    ) -> Tuple[list, float]:
        return top_rows_with_other(summary, limit=limit)

    @classmethod
    def _color_for_title(cls, title: str) -> object:
        return color_for_title(title)

    @classmethod
    def _color_name_for_title(cls, title: str) -> str:
        return color_name_for_title(title)

    def _build_bar_chart(self, summary: ReportSummary) -> object:
        return self._get_chart_builder().build_bar_chart(summary)

    def _build_pie_chart(self, summary: ReportSummary) -> object:
        return self._get_chart_builder().build_pie_chart(summary)

    def _populate_trend_chart(self, series_list: List[TrendSeries]) -> None:
        self._get_chart_builder().populate_trend_chart(
            self.trend_chart_view,
            series_list,
        )

    def _build_line_chart(self, series_list: List[TrendSeries]) -> object:
        return self._get_chart_builder().build_line_chart(series_list)
