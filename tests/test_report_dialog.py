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


if __name__ == "__main__":
    unittest.main()
