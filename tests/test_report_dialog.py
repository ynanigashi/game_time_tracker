import unittest
from datetime import date
from types import SimpleNamespace

from tests.test_stubs import install_stubs

install_stubs()

from PySide6.QtWidgets import QLabel, QTableWidget

from src.core.reporting import TrendPoint, TrendSeries
from src.ui.report_dialog import ReportDialog


class TestReportDialogDateRanges(unittest.TestCase):
    def test_this_week_starts_on_monday(self):
        today = date(2026, 4, 26)  # Sunday

        start, end = ReportDialog.date_range_for_period("this_week", today)

        self.assertEqual(start, date(2026, 4, 20))
        self.assertEqual(end, today)

    def test_this_month_starts_on_first_day(self):
        today = date(2026, 4, 26)

        start, end = ReportDialog.date_range_for_period("this_month", today)

        self.assertEqual(start, date(2026, 4, 1))
        self.assertEqual(end, today)

    def test_this_quarter_starts_on_quarter_first_month(self):
        today = date(2026, 4, 26)

        start, end = ReportDialog.date_range_for_period("this_quarter", today)

        self.assertEqual(start, date(2026, 4, 1))
        self.assertEqual(end, today)

    def test_this_half_starts_on_first_half_boundary(self):
        today = date(2026, 4, 26)

        start, end = ReportDialog.date_range_for_period("this_half", today)

        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, today)

    def test_this_half_starts_on_second_half_boundary(self):
        today = date(2026, 8, 15)

        start, end = ReportDialog.date_range_for_period("this_half", today)

        self.assertEqual(start, date(2026, 7, 1))
        self.assertEqual(end, today)

    def test_this_year_starts_on_january_first(self):
        today = date(2026, 4, 26)

        start, end = ReportDialog.date_range_for_period("this_year", today)

        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, today)

    def test_all_has_open_range(self):
        self.assertEqual(
            ReportDialog.date_range_for_period("all", date(2026, 4, 26)),
            (None, None),
        )

    def test_recent_day_ranges_are_inclusive(self):
        today = date(2026, 4, 26)

        self.assertEqual(
            ReportDialog.date_range_for_period("last_60_days", today),
            (date(2026, 2, 26), today),
        )
        self.assertEqual(
            ReportDialog.date_range_for_period("last_120_days", today),
            (date(2025, 12, 28), today),
        )
        self.assertEqual(
            ReportDialog.date_range_for_period("last_180_days", today),
            (date(2025, 10, 29), today),
        )
        self.assertEqual(
            ReportDialog.date_range_for_period("last_365_days", today),
            (date(2025, 4, 27), today),
        )


class TestReportDialogSyncMessages(unittest.TestCase):
    def test_sync_result_message_includes_detail_counts_and_error(self):
        dialog = ReportDialog.__new__(ReportDialog)
        dialog._cached_records = lambda: []
        result = SimpleNamespace(
            remote_count=10,
            imported=6,
            import_skipped=2,
            pending_count=3,
            backed_up=2,
            backup_failed=1,
            overwritten=1,
            reissued=1,
            total=8,
            error_message="network error",
        )

        message = dialog._sync_result_message(result)

        self.assertIn("スプシ同期一部失敗", message)
        self.assertIn("取得 10 件", message)
        self.assertIn("取込スキップ 2 件", message)
        self.assertIn("バックアップ失敗 1 件", message)
        self.assertIn("上書き 1 件", message)
        self.assertIn("別ID 1 件", message)
        self.assertIn("注意: network error", message)


class TestReportDialogLazyRefresh(unittest.TestCase):
    def _dialog(self, current_index=0):
        dialog = ReportDialog.__new__(ReportDialog)
        dialog._loaded_tabs = set()
        dialog._dirty_tabs = set()
        dialog._title_filter_dirty = False
        dialog.tabs = SimpleNamespace(currentIndex=lambda: current_index)
        dialog.refresh_summary_calls = 0
        dialog.refresh_trend_tab_calls = 0
        dialog.refresh_logs_calls = 0
        dialog.refresh_summary = lambda *args: setattr(
            dialog,
            "refresh_summary_calls",
            dialog.refresh_summary_calls + 1,
        )
        dialog.refresh_trend_tab = lambda *args: setattr(
            dialog,
            "refresh_trend_tab_calls",
            dialog.refresh_trend_tab_calls + 1,
        )
        dialog.refresh_logs = lambda *args: setattr(
            dialog,
            "refresh_logs_calls",
            dialog.refresh_logs_calls + 1,
        )
        return dialog

    def test_refresh_marks_all_tabs_dirty_and_refreshes_visible_tab_only(self):
        dialog = self._dialog(current_index=ReportDialog._TREND_TAB)

        dialog.refresh()

        self.assertEqual(dialog.refresh_summary_calls, 0)
        self.assertEqual(dialog.refresh_trend_tab_calls, 1)
        self.assertEqual(dialog.refresh_logs_calls, 0)
        self.assertIn(ReportDialog._TREND_TAB, dialog._loaded_tabs)
        self.assertNotIn(ReportDialog._TREND_TAB, dialog._dirty_tabs)
        self.assertIn(ReportDialog._SUMMARY_TAB, dialog._dirty_tabs)
        self.assertIn(ReportDialog._LOG_TAB, dialog._dirty_tabs)

    def test_clean_tab_change_does_not_recompute(self):
        dialog = self._dialog(current_index=ReportDialog._SUMMARY_TAB)
        dialog._loaded_tabs = {ReportDialog._LOG_TAB}

        dialog._on_tab_changed(ReportDialog._LOG_TAB)

        self.assertEqual(dialog.refresh_logs_calls, 0)

    def test_dirty_tab_change_refreshes_once(self):
        dialog = self._dialog(current_index=ReportDialog._SUMMARY_TAB)
        dialog._loaded_tabs = {ReportDialog._LOG_TAB}
        dialog._dirty_tabs = {ReportDialog._LOG_TAB}

        dialog._on_tab_changed(ReportDialog._LOG_TAB)

        self.assertEqual(dialog.refresh_logs_calls, 1)
        self.assertNotIn(ReportDialog._LOG_TAB, dialog._dirty_tabs)

    def test_trend_tab_reuses_title_filter_summary_until_data_changes(self):
        dialog = ReportDialog.__new__(ReportDialog)
        calls = {"summary": 0, "sync": 0, "trend": 0}
        summary = SimpleNamespace(rows=[])
        dialog._title_filter_summary = None
        dialog._title_filter_dirty = True
        dialog._title_filter_initialized = False
        dialog.log_handler = SimpleNamespace(
            get_report_stats=lambda **kwargs: calls.__setitem__(
                "summary",
                calls["summary"] + 1,
            )
            or summary
        )
        dialog._cached_records = lambda: []
        dialog._sync_title_filter = lambda value: calls.__setitem__(
            "sync",
            calls["sync"] + 1,
        )
        dialog.refresh_trend = lambda *args: calls.__setitem__(
            "trend",
            calls["trend"] + 1,
        )

        dialog.refresh_trend_tab()
        dialog._title_filter_initialized = True
        dialog.refresh_trend_tab()

        self.assertEqual(calls["summary"], 1)
        self.assertEqual(calls["sync"], 1)
        self.assertEqual(calls["trend"], 2)


class TestReportDialogTrendPeriod(unittest.TestCase):
    def test_selected_trend_date_range_uses_trend_period_combo(self):
        dialog = ReportDialog.__new__(ReportDialog)
        dialog.trend_period_combo = SimpleNamespace(currentData=lambda: "last_30_days")

        start, end = dialog._selected_trend_date_range()

        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        self.assertEqual((end - start).days, 29)

    def test_total_trend_passes_selected_date_range_to_log_handler(self):
        captured = {}

        class LogHandler:
            def get_trend_stats(self, **kwargs):
                captured.update(kwargs)
                return []

        dialog = ReportDialog.__new__(ReportDialog)
        dialog.log_handler = LogHandler()
        dialog.trend_granularity_combo = SimpleNamespace(currentData=lambda: "month")
        dialog.trend_period_combo = SimpleNamespace(currentData=lambda: "last_60_days")

        dialog._load_total_trend_series()

        self.assertEqual(captured["granularity"], "month")
        self.assertIsNotNone(captured["start_date"])
        self.assertIsNotNone(captured["end_date"])
        self.assertEqual((captured["end_date"] - captured["start_date"]).days, 59)

    def test_title_trend_passes_selected_date_range_to_log_handler(self):
        captured = {}

        class LogHandler:
            def get_trend_stats_by_title(self, **kwargs):
                captured.update(kwargs)
                return []

        dialog = ReportDialog.__new__(ReportDialog)
        dialog.log_handler = LogHandler()
        dialog.trend_mode_combo = SimpleNamespace(currentData=lambda: "by_title")
        dialog.trend_granularity_combo = SimpleNamespace(currentData=lambda: "week")
        dialog.trend_period_combo = SimpleNamespace(currentData=lambda: "this_year")
        dialog._selected_titles = lambda: ["Game"]

        dialog._load_trend_series()

        self.assertEqual(captured["titles"], ["Game"])
        self.assertIsNotNone(captured["start_date"])
        self.assertIsNotNone(captured["end_date"])

    def test_custom_trend_date_range_uses_date_edits(self):
        dialog = ReportDialog.__new__(ReportDialog)
        dialog.trend_period_combo = SimpleNamespace(currentData=lambda: "custom")
        dialog.trend_start_date_edit = SimpleNamespace(date=lambda: date(2026, 2, 1))
        dialog.trend_end_date_edit = SimpleNamespace(date=lambda: date(2026, 3, 31))

        start, end = dialog._selected_trend_date_range()

        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 3, 31))


class TestReportDialogTrendChartSelection(unittest.TestCase):
    def _series(self):
        return [
            TrendSeries(
                title="Game",
                points=[
                    TrendPoint("2026/01", date(2026, 1, 1), date(2026, 1, 31), 60),
                    TrendPoint("2026/02", date(2026, 2, 1), date(2026, 2, 28), 120),
                    TrendPoint("2026/03", date(2026, 3, 1), date(2026, 3, 31), 180),
                ],
            )
        ]

    def test_filter_trend_series_by_indices_returns_selected_points(self):
        filtered = ReportDialog._filter_trend_series_by_indices(
            self._series(),
            1,
            2,
        )

        self.assertEqual([point.label for point in filtered[0].points], ["2026/02", "2026/03"])

    def test_populate_trend_selection_updates_summary_and_table(self):
        dialog = ReportDialog.__new__(ReportDialog)
        dialog._trend_selected_indices = (1, 2)
        dialog.trend_summary_label = QLabel("")
        dialog.trend_table = QTableWidget()
        dialog._trend_series_label = lambda: "系列"

        dialog._populate_trend_selection(self._series())

        self.assertIn("2026/02/01 - 2026/03/31", dialog.trend_summary_label.text())
        self.assertIn("00:05:00.0", dialog.trend_summary_label.text())
        self.assertEqual(dialog.trend_table.row_count, 2)

    def test_clear_trend_selection_resets_chart_zoom_and_table(self):
        class Chart:
            def __init__(self):
                self.zoom_reset_called = False

            def zoomReset(self):
                self.zoom_reset_called = True

        chart = Chart()
        dialog = ReportDialog.__new__(ReportDialog)
        dialog._trend_selected_indices = (1, 2)
        dialog._last_trend_series = self._series()
        dialog.trend_summary_label = QLabel("")
        dialog.trend_table = QTableWidget()
        dialog.clear_trend_selection_button = SimpleNamespace(setEnabled=lambda value: None)
        dialog.trend_chart_view = SimpleNamespace(chart=lambda: chart)
        dialog._trend_series_label = lambda: "系列"
        dialog._set_debug_message = lambda *args, **kwargs: None

        dialog._clear_trend_selection()

        self.assertIsNone(dialog._trend_selected_indices)
        self.assertTrue(chart.zoom_reset_called)
        self.assertEqual(dialog.trend_table.row_count, 3)


class TestReportDialogLogOperations(unittest.TestCase):
    def test_finish_log_edit_refreshes_only_log_table(self):
        dialog = ReportDialog.__new__(ReportDialog)
        calls = {"refresh": 0, "refresh_logs": 0, "message": ""}
        dialog.refresh = lambda *args: calls.__setitem__("refresh", calls["refresh"] + 1)
        dialog.refresh_logs = lambda *args: calls.__setitem__(
            "refresh_logs",
            calls["refresh_logs"] + 1,
        )
        dialog._set_debug_message = lambda message, **kwargs: calls.__setitem__(
            "message",
            message,
        )

        dialog._finish_log_edit(
            SimpleNamespace(
                local_updated=True,
                spreadsheet_updated=False,
                error_message="",
            )
        )

        self.assertEqual(calls["refresh"], 0)
        self.assertEqual(calls["refresh_logs"], 1)
        self.assertIn("ローカル", calls["message"])

    def test_finish_log_delete_refreshes_log_table(self):
        dialog = ReportDialog.__new__(ReportDialog)
        calls = {"refresh_logs": 0, "message": ""}
        dialog.refresh_logs = lambda *args: calls.__setitem__(
            "refresh_logs",
            calls["refresh_logs"] + 1,
        )
        dialog._set_debug_message = lambda message, **kwargs: calls.__setitem__(
            "message",
            message,
        )

        dialog._finish_log_delete(
            SimpleNamespace(
                local_deleted=True,
                spreadsheet_deleted=True,
                error_message="",
            )
        )

        self.assertEqual(calls["refresh_logs"], 1)
        self.assertIn("削除", calls["message"])

    def test_delete_selected_log_record_starts_delete_after_confirmation(self):
        dialog = ReportDialog.__new__(ReportDialog)
        captured = {}
        dialog._selected_log_row = lambda: 0
        dialog._log_table_text = lambda row, column: "record-1" if column == 0 else ""
        dialog._confirm_delete_log_record = lambda row: True
        dialog._start_log_delete = lambda record_id: captured.setdefault(
            "record_id",
            record_id,
        )

        dialog._delete_selected_log_record()

        self.assertEqual(captured["record_id"], "record-1")


if __name__ == "__main__":
    unittest.main()
