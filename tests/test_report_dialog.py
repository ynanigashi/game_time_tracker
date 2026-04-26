import unittest
from datetime import date
from types import SimpleNamespace

from tests.test_stubs import install_stubs

install_stubs()

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


if __name__ == "__main__":
    unittest.main()
