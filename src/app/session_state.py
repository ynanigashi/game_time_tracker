"""Runtime game session state for MainWindow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List

from src.core.models import GameEntry


@dataclass
class GameSessionState:
    """Mutable scan/session state owned by MainWindow."""

    games: List[GameEntry] = field(default_factory=list)
    active_games_cache: List[GameEntry] = field(default_factory=list)
    inactive_games_cache: List[GameEntry] = field(default_factory=list)
    latest_window_titles: List[str] = field(default_factory=list)

    def update_scan_result(
        self,
        *,
        active_games: Iterable[GameEntry],
        inactive_games: Iterable[GameEntry],
        window_titles: Iterable[str],
    ) -> None:
        """Replace scan-derived caches from one completed scan."""
        self.active_games_cache = list(active_games)
        self.inactive_games_cache = list(inactive_games)
        self.latest_window_titles = list(window_titles)
