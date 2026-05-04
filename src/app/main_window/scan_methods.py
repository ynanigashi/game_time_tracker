"""Scan and today-summary action proxies for MainWindow."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

from src.app.main_window.base import MainWindowCollaborator

if TYPE_CHECKING:
    from src.core.domain import ScanResult
    from src.core.models import GameEntry

logger = logging.getLogger(__name__)


class MainWindowScanOps(MainWindowCollaborator):
    """Compatibility methods that delegate scan and today-summary work."""

    def _scan_tick(self) -> None:
        """Run one monitoring scan tick."""
        if not self._state.games:
            return

        if self._owner.daily_stats.check_day_change():
            self._owner.w.today_games_table.setRowCount(0)
            self._owner._prime_overtime_alert_progress(0.0)

        window_titles = self._owner.scanner.get_titles()
        foreground_title = self._owner.scanner.get_foreground_title()
        result = self._scan_games(window_titles, foreground_title)
        self._apply_scan_result(window_titles, result)

    def _scan_games(
            self,
            window_titles: List[str],
            foreground_title: Optional[str]) -> ScanResult:
        """Return game scan result for the current titles."""
        return self._owner._get_scan_controller().scan_games(
            window_titles,
            foreground_title,
        )

    def _apply_scan_result(self, window_titles: List[str], result: ScanResult) -> None:
        """Apply scan result to caches and UI."""
        self._owner._get_scan_controller().apply_scan_result(window_titles, result)

    def _update_scan_status(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> None:
        """Update the status message for the latest scan result."""
        self._owner._get_scan_controller().update_scan_status(
            active_games,
            inactive_games,
        )

    def _update_active_list(
            self,
            active_games: List[GameEntry],
            inactive_games: List[GameEntry]) -> None:
        """Update the currently playing game list."""
        self._owner._get_ui_controller().update_active_list(
            active_games,
            inactive_games,
        )

    def _all_playing_games(
            self,
            active_games: Optional[Sequence[GameEntry]] = None) -> List[GameEntry]:
        """Return active and recently inactive games that are still counted."""
        active = active_games if active_games is not None else self._state.active_games_cache
        return self._owner._get_ui_controller().all_playing_games(
            active,
            self._state.inactive_games_cache,
        )

    def _has_playing_games(self) -> bool:
        return any(
            bool(getattr(game, "is_playing", False))
            for game in self._state.games
        )

    def _update_session_times(
            self,
            active_games: List[GameEntry],
            now: datetime) -> None:
        """Update current session duration display."""
        self._owner._get_ui_controller().update_session_times(
            active_games,
            self._state.inactive_games_cache,
            now,
        )

    def _update_today_totals(
            self,
            active_games: List[GameEntry],
            now: datetime) -> float:
        """Update today's play total display."""
        return self._owner._get_ui_controller().update_today_totals(
            active_games,
            self._state.inactive_games_cache,
            now,
        )

    def _update_window_list(self, window_titles: List[str]) -> None:
        """Update the visible current-window-title list."""
        self._owner._get_ui_controller().update_window_list(window_titles)

    def _load_today_game_minutes(self) -> Dict[str, float]:
        """Load today's completed minutes by game from the log handler."""
        try:
            game_minutes, _ = self._owner.recorder.log_handler.get_today_stats()
            return game_minutes
        except Exception:
            logger.warning(
                "failed to load today's game minutes",
                exc_info=True,
            )
            return {}

    def _update_today_games_list(self, now: datetime) -> None:
        """Update today's played-game list."""
        self._owner._get_ui_controller().update_today_games_list(
            self._state.active_games_cache,
            self._state.inactive_games_cache,
            now,
        )

    def _load_today_completed_seconds(self) -> float:
        """Load today's completed play seconds from the log handler."""
        try:
            _, completed_seconds = self._owner.recorder.log_handler.get_today_stats()
            return completed_seconds
        except Exception:
            logger.warning(
                "failed to load today's completed play seconds",
                exc_info=True,
            )
            return 0.0
