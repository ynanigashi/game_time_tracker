"""Refresh orchestration for the report dialog."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import TYPE_CHECKING

from src.core.reporting import ReportSummary
from src.ui.report_sync_messages import sync_result_message

if TYPE_CHECKING:
    from src.ui.report_dialog import ReportDialog


logger = logging.getLogger(__name__)


class ReportRefreshController:
    """Refresh report tabs and synchronize cached spreadsheet records."""

    def __init__(self, owner: "ReportDialog") -> None:
        self.owner = owner

    def sync_from_spreadsheet(self) -> None:
        sync_with_spreadsheet = getattr(
            self.owner.log_handler,
            "sync_with_spreadsheet",
            None,
        )
        if not callable(sync_with_spreadsheet):
            self.owner._set_debug_message("スプシ同期に対応していないログハンドラです")
            return

        self.owner._set_debug_message("スプシ同期中...", process_events=True)
        try:
            result = sync_with_spreadsheet()
        except Exception:
            logger.exception("Failed to sync play logs from spreadsheet")
            self.owner._set_debug_message("スプシ同期に失敗しました")
            return

        self.owner.refresh()
        self.owner._set_debug_message(self.sync_result_message(result))

    def sync_result_message(self, result: object) -> str:
        return sync_result_message(result, lambda: len(self.owner._cached_records()))

    def refresh_summary(self) -> None:
        started_at = perf_counter()
        try:
            summary = self.owner._load_summary()
        except Exception:
            logger.exception("Failed to load report stats")
            summary = ReportSummary(rows=[], total_seconds=0.0, session_count=0)
        self.owner._ensure_report_tab_state().last_summary = summary

        self.owner._populate_summary(summary)
        self.owner._populate_chart(summary)
        elapsed_ms = (perf_counter() - started_at) * 1000
        self.owner._set_debug_message(
            f"ゲーム別集計を更新: {len(summary.rows)} タイトル "
            f"({elapsed_ms:.0f} ms)"
        )

    def refresh_trend(self) -> None:
        self.owner._trend_selected_indices = None
        started_at = perf_counter()
        try:
            series_list = self.owner._load_trend_series()
        except Exception:
            logger.exception("Failed to load trend stats")
            series_list = []
        self.owner._ensure_report_tab_state().last_trend_series = series_list

        self.owner._populate_trend_selection(series_list)
        self.owner._populate_trend_chart(series_list)
        self.owner._update_title_filter_action_states()
        self.owner._update_trend_selection_action_states()
        point_count = sum(len(series.points) for series in series_list)
        elapsed_ms = (perf_counter() - started_at) * 1000
        self.owner._set_debug_message(
            f"推移グラフを更新: {len(series_list)} {self.owner._trend_series_label()} / "
            f"{point_count} 点 ({elapsed_ms:.0f} ms)"
        )

    def refresh_logs(self) -> None:
        records = self.owner._cached_records()
        self.owner.log_summary_label.setText(f"ログ {len(records)} 件")
        self.owner._populate_log_table(records)
        self.owner._apply_selected_log_row()
