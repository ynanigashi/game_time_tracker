"""Layout construction helpers for the report dialog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src.ui.report_dialog import ReportDialog


def build_report_dialog_layout(dialog: "ReportDialog") -> None:
    """Build and attach the report dialog tab layout."""

    tabs = QTabWidget(dialog)
    tabs.addTab(build_summary_tab(dialog), "ゲーム別")
    tabs.addTab(build_trend_tab(dialog), "推移")
    tabs.addTab(build_log_tab(dialog), "ログ")
    tabs.currentChanged.connect(dialog._on_tab_changed)
    dialog.tabs = tabs

    layout = QVBoxLayout()
    layout.addWidget(tabs)
    layout.addWidget(dialog.debug_label)
    dialog.setLayout(layout)


def build_summary_tab(dialog: "ReportDialog") -> QWidget:
    controls = QHBoxLayout()
    controls.addWidget(QLabel("期間", dialog))
    controls.addWidget(dialog.period_combo)
    controls.addSpacing(12)
    controls.addWidget(QLabel("グラフ", dialog))
    controls.addWidget(dialog.chart_type_combo)
    controls.addSpacing(12)
    controls.addWidget(QLabel("単位", dialog))
    controls.addWidget(dialog.summary_unit_control)
    controls.addStretch()

    layout = QVBoxLayout()
    layout.addLayout(controls)
    layout.addWidget(dialog.summary_label)
    if dialog.chart_view is not None:
        layout.addWidget(dialog.chart_view, 2)
    elif dialog.chart_fallback_label is not None:
        layout.addWidget(dialog.chart_fallback_label)
    layout.addWidget(dialog.table, 3)

    tab = QWidget(dialog)
    tab.setLayout(layout)
    return tab


def build_trend_tab(dialog: "ReportDialog") -> QWidget:
    controls = QHBoxLayout()
    controls.addWidget(QLabel("期間", dialog))
    controls.addWidget(dialog.trend_period_combo)
    controls.addSpacing(12)
    controls.addWidget(QLabel("開始", dialog))
    controls.addWidget(dialog.trend_start_date_edit)
    controls.addWidget(QLabel("終了", dialog))
    controls.addWidget(dialog.trend_end_date_edit)
    controls.addWidget(dialog.trend_apply_date_button)
    controls.addSpacing(12)
    controls.addWidget(QLabel("表示", dialog))
    controls.addWidget(dialog.trend_mode_combo)
    controls.addSpacing(12)
    controls.addWidget(QLabel("集計単位", dialog))
    controls.addWidget(dialog.trend_granularity_combo)
    controls.addSpacing(12)
    controls.addWidget(QLabel("単位", dialog))
    controls.addWidget(dialog.trend_unit_control)
    controls.addSpacing(12)
    controls.addWidget(dialog.clear_trend_selection_button)
    controls.addStretch()

    layout = QVBoxLayout()
    layout.addLayout(controls)
    layout.addWidget(dialog.trend_summary_label)

    title_filter_layout = QVBoxLayout()
    title_filter_layout.addWidget(dialog.title_filter_label)
    title_filter_actions = QHBoxLayout()
    title_filter_actions.addWidget(dialog.select_all_titles_button)
    title_filter_actions.addWidget(dialog.clear_all_titles_button)
    title_filter_layout.addLayout(title_filter_actions)
    title_filter_layout.addWidget(dialog.title_filter_table)

    trend_layout = QVBoxLayout()
    if dialog.trend_chart_view is not None:
        trend_layout.addWidget(dialog.trend_chart_view, 3)
    trend_layout.addWidget(dialog.trend_table, 2)

    content_layout = QHBoxLayout()
    content_layout.addLayout(title_filter_layout, 1)
    content_layout.addLayout(trend_layout, 4)
    layout.addLayout(content_layout)

    tab = QWidget(dialog)
    tab.setLayout(layout)
    return tab


def build_log_tab(dialog: "ReportDialog") -> QWidget:
    controls = QHBoxLayout()
    controls.addWidget(dialog.log_sync_button)
    controls.addWidget(dialog.log_edit_button)
    controls.addWidget(dialog.log_delete_button)
    controls.addStretch()

    form = QFormLayout()
    form.addRow("開始時刻", dialog.log_start_time_edit)
    form.addRow("終了時刻", dialog.log_end_time_edit)
    form.addRow("タイトル", dialog.log_title_edit)
    form.addRow("フレンドとプレイ", dialog.log_friends_check)

    layout = QVBoxLayout()
    layout.addLayout(controls)
    layout.addWidget(dialog.log_summary_label)
    layout.addWidget(dialog.log_table)
    layout.addLayout(form)

    tab = QWidget(dialog)
    tab.setLayout(layout)
    return tab
