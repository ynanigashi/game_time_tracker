"""MainWindow timer and tick orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget


class MainWindowLoopController:
    """MainWindow のタイマー起動と tick オーケストレーション."""

    def __init__(self, timer_factory: Callable[[QWidget], QTimer] = QTimer) -> None:
        self._timer_factory = timer_factory

    def start_timer(
        self,
        owner: QWidget,
        interval_seconds: float,
        callback: Callable[[], None],
    ) -> QTimer:
        """タイマーを作成して開始."""
        timer = self._timer_factory(owner)
        timer.setInterval(int(interval_seconds * 1000))
        timer.timeout.connect(callback)
        timer.start()
        return timer

    def run_scan_tick(self, window: "MainWindow") -> None:
        """監視サイクル（1秒間隔）."""
        if not window.games:
            return

        if window.daily_stats.check_day_change():
            window.w.today_games_table.setRowCount(0)
            window._prime_overtime_alert_progress(0.0)

        window_titles = window.scanner.get_titles()
        foreground_title = window.scanner.get_foreground_title()
        result = window._scan_games(window_titles, foreground_title)
        window._apply_scan_result(window_titles, result)

    def run_ui_tick(self, window: "MainWindow") -> None:
        """UIだけを高速更新（0.1秒間隔）."""
        now = datetime.now()
        window._update_session_times(window.active_games_cache, now)
        total_seconds = window._update_today_totals(window.active_games_cache, now)
        window._update_today_games_list(now)
        window._update_overtime_alert(total_seconds)
