"""時刻関連のユーティリティ関数."""

from datetime import datetime, time, timedelta
from typing import List, Tuple

# 定数
SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
TIME_FRACTION_PRECISION = 10  # 0.1秒単位での時間表示精度
GSS_DATETIME_FORMAT = "%Y/%m/%d %H:%M:%S"


def format_hms(total_seconds: float) -> str:
    """秒を HH:MM:SS.F 形式に整形（Fは0.1秒単位）.
    
    Args:
        total_seconds: 秒数（浮動小数点数）
    
    Returns:
        "HH:MM:SS.F" 形式の文字列
    
    Examples:
        >>> format_hms(0)
        '00:00:00.0'
        >>> format_hms(3661.75)
        '01:01:01.7'
        >>> format_hms(37845.25)
        '10:30:45.2'
    """
    seconds_int = int(total_seconds)
    minutes, seconds_int = divmod(seconds_int, SECONDS_PER_MINUTE)
    hours, minutes = divmod(minutes, MINUTES_PER_HOUR)
    fraction = int((total_seconds - int(total_seconds)) * TIME_FRACTION_PRECISION)
    return f'{hours:02}:{minutes:02}:{seconds_int:02}.{fraction}'


def split_by_day(start: datetime, end: datetime) -> List[Tuple[datetime, datetime]]:
    """セッションを日付境界で分割.
    
    Args:
        start: セッション開始時刻
        end: セッション終了時刻
    
    Returns:
        日付境界で分割されたセグメントのリスト
    
    Examples:
        >>> start = datetime(2026, 1, 10, 23, 30, 0)
        >>> end = datetime(2026, 1, 11, 1, 30, 0)
        >>> segments = split_by_day(start, end)
        >>> len(segments)
        2
        >>> segments[0][0]
        datetime.datetime(2026, 1, 10, 23, 30, 0)
        >>> segments[1][0]
        datetime.datetime(2026, 1, 11, 0, 0, 0)
    """
    segments: List[Tuple[datetime, datetime]] = []
    current_start = start

    while current_start.date() < end.date():
        # 当日の終わり（23:59:59.999999）
        day_end = datetime.combine(
            current_start.date(),
            time(23, 59, 59, 999999),
        )
        segments.append((current_start, day_end))
        # 翌日の開始（00:00:00）
        current_start = datetime.combine(
            current_start.date() + timedelta(days=1),
            time(0, 0, 0),
        )

    segments.append((current_start, end))
    return segments


def calc_today_elapsed_seconds(start_time: datetime, now: datetime) -> float:
    """ゲームの今日分の経過秒数を計算（日跨ぎ対応）.
    
    Args:
        start_time: セッション開始時刻
        now: 現在時刻
    
    Returns:
        今日分の経過秒数
    
    Examples:
        >>> now = datetime(2026, 1, 18, 10, 0, 0)
        >>> # 今日の8時に開始した場合
        >>> start = datetime(2026, 1, 18, 8, 0, 0)
        >>> calc_today_elapsed_seconds(start, now)
        7200.0
        >>> # 昨日の23時に開始した場合（今日分は10時間）
        >>> start = datetime(2026, 1, 17, 23, 0, 0)
        >>> calc_today_elapsed_seconds(start, now)
        36000.0
    """
    today_start = datetime.combine(now.date(), time(0, 0, 0))
    effective_start = max(start_time, today_start)
    return (now - effective_start).total_seconds()
