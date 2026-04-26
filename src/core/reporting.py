"""Report aggregation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional

from src.core.models import parse_record


@dataclass(frozen=True)
class GameReportRow:
    """Aggregated play statistics for one game."""

    game_title: str
    total_seconds: float
    session_count: int
    last_played: Optional[datetime]

    @property
    def average_seconds(self) -> float:
        if self.session_count <= 0:
            return 0.0
        return self.total_seconds / self.session_count


@dataclass(frozen=True)
class ReportSummary:
    """Aggregated play statistics for a report period."""

    rows: List[GameReportRow]
    total_seconds: float
    session_count: int


@dataclass(frozen=True)
class TrendPoint:
    """Aggregated play time for one trend bucket."""

    label: str
    start_date: date
    end_date: date
    total_seconds: float


@dataclass(frozen=True)
class TrendSeries:
    """Aggregated play-time trend points for one game title."""

    title: str
    points: List[TrendPoint]


@dataclass(frozen=True)
class _PlaySession:
    title: str
    start: datetime
    end: datetime
    seconds: float


def _iter_play_sessions(
    records: Iterable[dict],
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Iterable[_PlaySession]:
    for record in records:
        parsed = parse_record(record)
        if parsed is None:
            continue

        record_date = parsed.start.date()
        if start_date is not None and record_date < start_date:
            continue
        if end_date is not None and record_date > end_date:
            continue

        seconds = max(0.0, (parsed.end - parsed.start).total_seconds())
        if seconds <= 0:
            continue

        yield _PlaySession(
            title=parsed.game_title,
            start=parsed.start,
            end=parsed.end,
            seconds=seconds,
        )


def _period_start(value: date, granularity: str) -> date:
    if granularity == "week":
        return value - timedelta(days=value.weekday())
    if granularity == "month":
        return value.replace(day=1)
    if granularity == "quarter":
        month = ((value.month - 1) // 3) * 3 + 1
        return date(value.year, month, 1)
    if granularity == "half":
        month = 1 if value.month <= 6 else 7
        return date(value.year, month, 1)
    if granularity == "year":
        return date(value.year, 1, 1)
    raise ValueError(f"Unsupported trend granularity: {granularity}")


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)


def _next_period_start(value: date, granularity: str) -> date:
    if granularity == "week":
        return value + timedelta(days=7)
    if granularity == "month":
        return _add_months(value, 1)
    if granularity == "quarter":
        return _add_months(value, 3)
    if granularity == "half":
        return _add_months(value, 6)
    if granularity == "year":
        return date(value.year + 1, 1, 1)
    raise ValueError(f"Unsupported trend granularity: {granularity}")


def _period_label(value: date, granularity: str) -> str:
    if granularity == "week":
        return f"{value:%Y/%m/%d}"
    if granularity == "month":
        return f"{value:%Y/%m}"
    if granularity == "quarter":
        quarter = ((value.month - 1) // 3) + 1
        return f"{value.year} Q{quarter}"
    if granularity == "half":
        half = 1 if value.month <= 6 else 2
        return f"{value.year} H{half}"
    if granularity == "year":
        return f"{value.year}"
    raise ValueError(f"Unsupported trend granularity: {granularity}")


def _period_starts_between(
    start: date,
    end: date,
    granularity: str,
) -> List[date]:
    period_starts: List[date] = []
    current = start
    while current <= end:
        period_starts.append(current)
        current = _next_period_start(current, granularity)
    return period_starts


def _trend_points_from_buckets(
    period_starts: Iterable[date],
    bucket_seconds: Dict[date, float],
    granularity: str,
) -> List[TrendPoint]:
    points: List[TrendPoint] = []
    for period_start in period_starts:
        next_start = _next_period_start(period_start, granularity)
        points.append(
            TrendPoint(
                label=_period_label(period_start, granularity),
                start_date=period_start,
                end_date=next_start - timedelta(days=1),
                total_seconds=bucket_seconds.get(period_start, 0.0),
            )
        )
    return points


def build_game_report(
    records: Iterable[dict],
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> ReportSummary:
    """Build a game report from cached play log records.

    Records are already split by day when they are written, so filtering by the
    start date is enough for the current storage model.
    """
    totals: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    last_played: Dict[str, datetime] = {}
    total_seconds = 0.0
    session_count = 0

    for session in _iter_play_sessions(
        records,
        start_date=start_date,
        end_date=end_date,
    ):
        title = session.title
        totals[title] = totals.get(title, 0.0) + session.seconds
        counts[title] = counts.get(title, 0) + 1
        if title not in last_played or session.end > last_played[title]:
            last_played[title] = session.end

        total_seconds += session.seconds
        session_count += 1

    rows = [
        GameReportRow(
            game_title=title,
            total_seconds=seconds,
            session_count=counts[title],
            last_played=last_played.get(title),
        )
        for title, seconds in totals.items()
    ]
    rows.sort(key=lambda row: (-row.total_seconds, row.game_title.casefold()))
    return ReportSummary(
        rows=rows,
        total_seconds=total_seconds,
        session_count=session_count,
    )


def build_play_time_trend(
    records: Iterable[dict],
    *,
    granularity: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[TrendPoint]:
    """Build total play-time trend points by period."""
    bucket_seconds: Dict[date, float] = {}
    min_bucket: Optional[date] = None
    max_bucket: Optional[date] = None

    for session in _iter_play_sessions(
        records,
        start_date=start_date,
        end_date=end_date,
    ):
        bucket = _period_start(session.start.date(), granularity)
        bucket_seconds[bucket] = bucket_seconds.get(bucket, 0.0) + session.seconds
        min_bucket = bucket if min_bucket is None else min(min_bucket, bucket)
        max_bucket = bucket if max_bucket is None else max(max_bucket, bucket)

    if min_bucket is None or max_bucket is None:
        return []

    return _trend_points_from_buckets(
        _period_starts_between(min_bucket, max_bucket, granularity),
        bucket_seconds,
        granularity,
    )


def build_play_time_trend_by_title(
    records: Iterable[dict],
    *,
    granularity: str,
    titles: Optional[Iterable[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[TrendSeries]:
    """Build play-time trend points grouped by game title.

    All returned series share the same period range so they can be plotted on
    one chart.
    """
    selected_titles = set(titles) if titles is not None else None
    if selected_titles is not None and not selected_titles:
        return []

    bucket_seconds_by_title: Dict[str, Dict[date, float]] = {}
    min_bucket: Optional[date] = None
    max_bucket: Optional[date] = None

    for session in _iter_play_sessions(
        records,
        start_date=start_date,
        end_date=end_date,
    ):
        title = session.title
        if selected_titles is not None and title not in selected_titles:
            continue

        bucket = _period_start(session.start.date(), granularity)
        title_buckets = bucket_seconds_by_title.setdefault(title, {})
        title_buckets[bucket] = title_buckets.get(bucket, 0.0) + session.seconds
        min_bucket = bucket if min_bucket is None else min(min_bucket, bucket)
        max_bucket = bucket if max_bucket is None else max(max_bucket, bucket)

    if min_bucket is None or max_bucket is None:
        return []

    period_starts = _period_starts_between(min_bucket, max_bucket, granularity)

    def total_for_title(title: str) -> float:
        return sum(bucket_seconds_by_title[title].values())

    series_list: List[TrendSeries] = []
    for title in sorted(
        bucket_seconds_by_title,
        key=lambda value: (-total_for_title(value), value.casefold()),
    ):
        title_buckets = bucket_seconds_by_title[title]
        points = _trend_points_from_buckets(
            period_starts,
            title_buckets,
            granularity,
        )
        series_list.append(TrendSeries(title=title, points=points))

    return series_list
