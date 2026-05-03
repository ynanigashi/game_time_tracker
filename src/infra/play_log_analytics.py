"""Analytics helpers for cached play-log records."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from src.core.models import parse_record
from src.core.reporting import (
    ReportSummary,
    TrendPoint,
    TrendSeries,
    build_game_report,
    build_play_time_trend,
    build_play_time_trend_by_title,
)
from src.core.time_utils import SECONDS_PER_MINUTE

logger = logging.getLogger(__name__)


class PlayLogAnalytics:
    """Read-only analytics over cached play-log records."""

    def __init__(self, records: List[Dict[str, object]]) -> None:
        self.records = records

    def get_today_stats(self) -> Tuple[Dict[str, float], float]:
        game_minutes: Dict[str, float] = {}
        total_seconds = 0.0
        parse_failed_count = 0
        today = datetime.now().date()

        try:
            for record in self.records:
                parsed = parse_record(record)
                if parsed is None:
                    parse_failed_count += 1
                    continue
                if parsed.start.date() != today:
                    continue

                seconds = (parsed.end - parsed.start).total_seconds()
                total_seconds += seconds

                minutes = seconds / SECONDS_PER_MINUTE
                game_minutes[parsed.game_title] = (
                    game_minutes.get(parsed.game_title, 0) + minutes
                )
        except Exception as exc:
            logger.error("failed to calculate today's play stats: %s", exc)
        if parse_failed_count:
            logger.debug(
                "get_today_stats skipped invalid records (count=%s)",
                parse_failed_count,
            )

        return game_minutes, total_seconds

    def get_report_stats(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> ReportSummary:
        return build_game_report(
            self.records,
            start_date=start_date,
            end_date=end_date,
        )

    def get_trend_stats(
        self,
        *,
        granularity: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[TrendPoint]:
        return build_play_time_trend(
            self.records,
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
        )

    def get_trend_stats_by_title(
        self,
        *,
        granularity: str,
        titles: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[TrendSeries]:
        return build_play_time_trend_by_title(
            self.records,
            granularity=granularity,
            titles=titles,
            start_date=start_date,
            end_date=end_date,
        )
