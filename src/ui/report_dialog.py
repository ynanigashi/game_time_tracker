"""Report dialog for cached play logs."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from src.ui.report_charts import (
    CHARTS_AVAILABLE,
    GAME_COLORS,
    create_chart_views,
)
from src.ui.report_date_ranges import RECENT_PERIOD_DAYS
from src.ui.report_dialog_data_mixins import ReportDialogDataMixin
from src.ui.report_dialog_refresh_mixins import ReportDialogRefreshMixin
from src.ui.report_dialog_state_mixins import ReportDialogStateMixin
from src.ui.report_layout import build_report_dialog_layout
from src.ui.report_graph_unit_state import ReportGraphUnitState
from src.ui.report_log_operation_state import ReportLogOperationState
from src.ui.report_tab_state import ReportTabState
from src.ui.report_title_filter_state import ReportTitleFilterState
from src.ui.report_trend_selection_state import ReportTrendSelectionState


class ReportDialog(
    ReportDialogStateMixin,
    ReportDialogDataMixin,
    ReportDialogRefreshMixin,
    QDialog,
):
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
        self._log_operation_state = ReportLogOperationState()
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

        self._graph_unit_state = ReportGraphUnitState()
        self._trend_selection_state = ReportTrendSelectionState()
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
        self._title_filter_state = ReportTitleFilterState()
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

        build_report_dialog_layout(self)
        self.refresh()
