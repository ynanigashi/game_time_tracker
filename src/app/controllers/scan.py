"""Game scanning orchestration for MainWindow."""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from src.core.adapters import Messages
from src.core.models import GameEntry
from src.core.domain import ScanResult

logger = logging.getLogger(__name__)


class ScanStateTracker(Protocol):
    """Minimal scan dependency required by MainWindowScanController."""

    def scan(
        self,
        *,
        games: Sequence[GameEntry],
        window_titles: List[str],
        foreground_title: Optional[str],
        load_today_game_minutes_callback: Callable[[], Dict[str, float]],
    ) -> ScanResult:
        ...


class MainWindowScanController:
    """Coordinates scan result application and scan-related cached stats."""

    def __init__(
        self,
        *,
        state_tracker: Optional[ScanStateTracker],
        games_provider: Callable[[], Sequence[GameEntry]],
        scan_result_updater: Callable[
            [Sequence[GameEntry], Sequence[GameEntry], List[str]],
            None,
        ],
        update_active_list: Callable[[List[GameEntry], List[GameEntry]], None],
        update_window_list: Callable[[List[str]], None],
        update_scan_status: Callable[[Sequence[GameEntry], Sequence[GameEntry]], None],
        set_status: Callable[[str], None],
        load_today_game_minutes: Callable[[], Dict[str, float]],
        get_today_stats: Callable[[], Tuple[Dict[str, float], float]],
    ) -> None:
        self.state_tracker = state_tracker
        self.games_provider = games_provider
        self.scan_result_updater = scan_result_updater
        self.update_active_list_callback = update_active_list
        self.update_window_list_callback = update_window_list
        self.update_scan_status_callback = update_scan_status
        self.set_status = set_status
        self.load_today_game_minutes_callback = load_today_game_minutes
        self.get_today_stats = get_today_stats

    def scan_games(
        self,
        window_titles: List[str],
        foreground_title: Optional[str],
    ) -> ScanResult:
        if self.state_tracker is None:
            raise RuntimeError("state_tracker is required to scan games")
        return self.state_tracker.scan(
            games=self.games_provider(),
            window_titles=window_titles,
            foreground_title=foreground_title,
            load_today_game_minutes_callback=self.load_today_game_minutes_callback,
        )

    def apply_scan_result(self, window_titles: List[str], result: ScanResult) -> None:
        self.scan_result_updater(
            result.active_games,
            result.inactive_games,
            window_titles,
        )
        self.update_active_list_callback(result.active_games, result.inactive_games)
        self.update_window_list_callback(window_titles)
        self.update_scan_status_callback(result.active_games, result.inactive_games)

    def update_scan_status(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> None:
        if active_games or inactive_games:
            self.set_status("プレイ時間計測中")
        else:
            self.set_status(Messages.NO_GAME_PLAYING)

    def has_playing_games(self) -> bool:
        return any(
            bool(getattr(game, "is_playing", False))
            for game in self.games_provider()
        )

    def load_today_game_minutes(self) -> Dict[str, float]:
        try:
            game_minutes, _ = self.get_today_stats()
            return game_minutes
        except Exception as e:
            logger.error("今日のゲーム時間の集計中にエラーが発生しました: %s", e)
            return {}

    def load_today_completed_seconds(self) -> float:
        try:
            _, completed_seconds = self.get_today_stats()
            return completed_seconds
        except Exception as e:
            logger.error("今日の完了プレイ時間のロード中にエラーが発生しました: %s", e)
            return 0.0
