import unittest
from datetime import date

from src.core.reporting import (
    build_game_report,
    build_play_time_trend,
    build_play_time_trend_by_title,
)


class TestBuildGameReport(unittest.TestCase):
    def test_aggregates_records_by_game(self):
        summary = build_game_report(
            [
                {
                    "start_time": "2026/01/18 10:00:00",
                    "end_time": "2026/01/18 10:30:00",
                    "title": "Game A",
                },
                {
                    "start_time": "2026/01/18 11:00:00",
                    "end_time": "2026/01/18 12:00:00",
                    "title": "Game B",
                },
                {
                    "start_time": "2026/01/19 10:00:00",
                    "end_time": "2026/01/19 10:15:00",
                    "title": "Game A",
                },
            ]
        )

        self.assertEqual(summary.session_count, 3)
        self.assertEqual(len(summary.rows), 2)
        self.assertEqual(summary.rows[0].game_title, "Game B")
        self.assertEqual(summary.rows[0].total_seconds, 60 * 60)
        self.assertEqual(summary.rows[0].session_count, 1)
        self.assertEqual(summary.rows[1].game_title, "Game A")
        self.assertEqual(summary.rows[1].total_seconds, 45 * 60)
        self.assertEqual(summary.rows[1].session_count, 2)

    def test_filters_by_date_range(self):
        summary = build_game_report(
            [
                {
                    "start_time": "2026/01/17 10:00:00",
                    "end_time": "2026/01/17 11:00:00",
                    "title": "Old",
                },
                {
                    "start_time": "2026/01/18 10:00:00",
                    "end_time": "2026/01/18 11:00:00",
                    "title": "In Range",
                },
            ],
            start_date=date(2026, 1, 18),
            end_date=date(2026, 1, 18),
        )

        self.assertEqual(summary.session_count, 1)
        self.assertEqual(summary.rows[0].game_title, "In Range")


class TestBuildPlayTimeTrend(unittest.TestCase):
    def test_weekly_trend_uses_monday_start(self):
        points = build_play_time_trend(
            [
                {
                    "start_time": "2026/04/20 10:00:00",
                    "end_time": "2026/04/20 11:00:00",
                    "title": "Game",
                },
                {
                    "start_time": "2026/04/26 10:00:00",
                    "end_time": "2026/04/26 10:30:00",
                    "title": "Game",
                },
            ],
            granularity="week",
        )

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].start_date, date(2026, 4, 20))
        self.assertEqual(points[0].end_date, date(2026, 4, 26))
        self.assertEqual(points[0].total_seconds, 90 * 60)

    def test_monthly_trend_fills_empty_periods(self):
        points = build_play_time_trend(
            [
                {
                    "start_time": "2026/01/18 10:00:00",
                    "end_time": "2026/01/18 11:00:00",
                    "title": "Game",
                },
                {
                    "start_time": "2026/03/18 10:00:00",
                    "end_time": "2026/03/18 12:00:00",
                    "title": "Game",
                },
            ],
            granularity="month",
        )

        self.assertEqual(
            [point.label for point in points],
            ["2026/01", "2026/02", "2026/03"],
        )
        self.assertEqual(points[0].total_seconds, 60 * 60)
        self.assertEqual(points[1].total_seconds, 0)
        self.assertEqual(points[2].total_seconds, 120 * 60)

    def test_quarter_half_and_year_labels(self):
        records = [
            {
                "start_time": "2026/08/15 10:00:00",
                "end_time": "2026/08/15 11:00:00",
                "title": "Game",
            }
        ]

        quarter = build_play_time_trend(records, granularity="quarter")
        half = build_play_time_trend(records, granularity="half")
        year = build_play_time_trend(records, granularity="year")

        self.assertEqual(quarter[0].label, "2026 Q3")
        self.assertEqual(half[0].label, "2026 H2")
        self.assertEqual(year[0].label, "2026")

    def test_title_trend_uses_common_periods_and_filters_titles(self):
        series_list = build_play_time_trend_by_title(
            [
                {
                    "start_time": "2026/01/18 10:00:00",
                    "end_time": "2026/01/18 11:00:00",
                    "title": "Game A",
                },
                {
                    "start_time": "2026/02/18 10:00:00",
                    "end_time": "2026/02/18 10:30:00",
                    "title": "Game B",
                },
                {
                    "start_time": "2026/03/18 10:00:00",
                    "end_time": "2026/03/18 12:00:00",
                    "title": "Game A",
                },
            ],
            granularity="month",
            titles=["Game A"],
        )

        self.assertEqual(len(series_list), 1)
        self.assertEqual(series_list[0].title, "Game A")
        self.assertEqual(
            [point.label for point in series_list[0].points],
            ["2026/01", "2026/02", "2026/03"],
        )
        self.assertEqual(series_list[0].points[0].total_seconds, 60 * 60)
        self.assertEqual(series_list[0].points[1].total_seconds, 0)
        self.assertEqual(series_list[0].points[2].total_seconds, 120 * 60)

    def test_title_trend_returns_empty_when_no_titles_are_selected(self):
        series_list = build_play_time_trend_by_title(
            [
                {
                    "start_time": "2026/01/18 10:00:00",
                    "end_time": "2026/01/18 11:00:00",
                    "title": "Game A",
                },
            ],
            granularity="month",
            titles=[],
        )

        self.assertEqual(series_list, [])


if __name__ == "__main__":
    unittest.main()
