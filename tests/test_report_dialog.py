import unittest
from datetime import date

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


if __name__ == "__main__":
    unittest.main()
