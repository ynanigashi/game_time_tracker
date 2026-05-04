"""MainWindow timer and tick orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional, Sequence, TypeVar

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from src.core.domain import ScanResult
from src.core.models import GameEntry

TCallback = TypeVar("TCallback")


def _require_callback(name: str, callback: Optional[TCallback]) -> TCallback:
    if callback is None:
        raise RuntimeError(f"MainWindowLoopController requires {name}")
    return callback


class MainWindowLoopController:
    """Start timers and orchestrate scan/UI ticks through injected collaborators."""

    def __init__(
        self,
        timer_factory: Callable[[QWidget], QTimer] = QTimer,
        *,
        games_provider: Optional[Callable[[], Sequence[GameEntry]]] = None,
        day_change_checker: Optional[Callable[[], bool]] = None,
        reset_today_games_table: Optional[Callable[[], None]] = None,
        prime_overtime_alert_progress: Optional[Callable[[float], None]] = None,
        window_titles_provider: Optional[Callable[[], list[str]]] = None,
        foreground_title_provider: Optional[Callable[[], Optional[str]]] = None,
        scan_games: Optional[Callable[[list[str], Optional[str]], ScanResult]] = None,
        apply_scan_result: Optional[Callable[[list[str], ScanResult], None]] = None,
        active_games_provider: Optional[Callable[[], list[GameEntry]]] = None,
        update_session_times: Optional[Callable[[list[GameEntry], datetime], None]] = None,
        update_today_totals: Optional[Callable[[list[GameEntry], datetime], float]] = None,
        update_today_games_list: Optional[Callable[[datetime], None]] = None,
        update_overtime_alert: Optional[Callable[[float], None]] = None,
        sync_overlay: Optional[Callable[[], None]] = None,
        now_provider: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._timer_factory = timer_factory
        self._games_provider = games_provider
        self._day_change_checker = day_change_checker
        self._reset_today_games_table = reset_today_games_table
        self._prime_overtime_alert_progress = prime_overtime_alert_progress
        self._window_titles_provider = window_titles_provider
        self._foreground_title_provider = foreground_title_provider
        self._scan_games = scan_games
        self._apply_scan_result = apply_scan_result
        self._active_games_provider = active_games_provider
        self._update_session_times = update_session_times
        self._update_today_totals = update_today_totals
        self._update_today_games_list = update_today_games_list
        self._update_overtime_alert = update_overtime_alert
        self._sync_overlay = sync_overlay
        self._now_provider = now_provider

    def start_timer(
        self,
        owner: QWidget,
        interval_seconds: float,
        callback: Callable[[], None],
    ) -> QTimer:
        """Create and start a Qt timer."""
        timer = self._timer_factory(owner)
        timer.setInterval(int(interval_seconds * 1000))
        timer.timeout.connect(callback)
        timer.start()
        return timer

    def run_scan_tick(self) -> None:
        """Run one monitoring scan tick."""
        games_provider = _require_callback("games_provider", self._games_provider)
        if not games_provider():
            return

        day_change_checker = _require_callback(
            "day_change_checker",
            self._day_change_checker,
        )
        if day_change_checker():
            _require_callback(
                "reset_today_games_table",
                self._reset_today_games_table,
            )()
            _require_callback(
                "prime_overtime_alert_progress",
                self._prime_overtime_alert_progress,
            )(0.0)

        window_titles = _require_callback(
            "window_titles_provider",
            self._window_titles_provider,
        )()
        foreground_title = _require_callback(
            "foreground_title_provider",
            self._foreground_title_provider,
        )()
        result = _require_callback("scan_games", self._scan_games)(
            window_titles,
            foreground_title,
        )
        _require_callback("apply_scan_result", self._apply_scan_result)(
            window_titles,
            result,
        )

    def run_ui_tick(self) -> None:
        """Run one high-frequency UI refresh tick."""
        now = self._now_provider()
        active_games = _require_callback(
            "active_games_provider",
            self._active_games_provider,
        )()
        _require_callback("update_session_times", self._update_session_times)(
            active_games,
            now,
        )
        total_seconds = _require_callback(
            "update_today_totals",
            self._update_today_totals,
        )(active_games, now)
        _require_callback("update_today_games_list", self._update_today_games_list)(now)
        _require_callback("update_overtime_alert", self._update_overtime_alert)(
            total_seconds,
        )
        _require_callback("sync_overlay", self._sync_overlay)()
