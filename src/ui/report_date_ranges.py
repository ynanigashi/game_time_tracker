"""Date-range helpers for report periods."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


RECENT_PERIOD_DAYS: Dict[str, int] = {
    "last_7_days": 7,
    "last_30_days": 30,
    "last_60_days": 60,
    "last_120_days": 120,
    "last_180_days": 180,
    "last_365_days": 365,
}


def date_range_for_period(
    period_key: str,
    today: date,
) -> Tuple[Optional[date], Optional[date]]:
    """Return inclusive start/end dates for a report period key."""
    if period_key == "all":
        return None, None
    if period_key == "today":
        return today, today
    if period_key == "this_week":
        return today - timedelta(days=today.weekday()), today
    if period_key == "this_month":
        return today.replace(day=1), today
    if period_key == "this_quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        return date(today.year, quarter_start_month, 1), today
    if period_key == "this_half":
        half_start_month = 1 if today.month <= 6 else 7
        return date(today.year, half_start_month, 1), today
    if period_key == "this_year":
        return date(today.year, 1, 1), today
    if period_key in RECENT_PERIOD_DAYS:
        days = RECENT_PERIOD_DAYS[period_key]
        return today - timedelta(days=days - 1), today

    logger.warning("Unknown report period: %s", period_key)
    return None, None
