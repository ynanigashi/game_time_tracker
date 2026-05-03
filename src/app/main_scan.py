"""Game scanning orchestration for MainWindow."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

from src.core.adapters import Messages
from src.core.models import GameEntry
from src.core.domain import ScanResult

logger = logging.getLogger(__name__)


class MainWindowScanController:
    """Coordinates scan result application and scan-related cached stats."""

    def __init__(self, owner: "MainWindow") -> None:
        self.owner = owner

    def scan_games(
        self,
        window_titles: List[str],
        foreground_title: Optional[str],
    ) -> ScanResult:
        return self.owner.state_tracker.scan(
            games=self.owner.games,
            window_titles=window_titles,
            foreground_title=foreground_title,
            load_today_game_minutes_callback=self.owner._load_today_game_minutes,
        )

    def apply_scan_result(self, window_titles: List[str], result: ScanResult) -> None:
        self.owner._ensure_session_state().update_scan_result(
            active_games=result.active_games,
            inactive_games=result.inactive_games,
            window_titles=window_titles,
        )
        self.owner._update_active_list(result.active_games, result.inactive_games)
        self.owner._update_window_list(window_titles)
        self.owner._update_scan_status(result.active_games, result.inactive_games)

    def update_scan_status(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> None:
        if active_games or inactive_games:
            self.owner._set_status("プレイ時間計測中")
        else:
            self.owner._set_status(Messages.NO_GAME_PLAYING)

    def has_playing_games(self) -> bool:
        return any(
            bool(getattr(game, "is_playing", False))
            for game in getattr(self.owner, "games", [])
        )

    def load_today_game_minutes(self) -> Dict[str, float]:
        try:
            game_minutes, _ = self.owner.recorder.log_handler.get_today_stats()
            return game_minutes
        except Exception as e:
            logger.error("今日のゲーム時間の集計中にエラーが発生しました: %s", e)
            return {}

    def load_today_completed_seconds(self) -> float:
        try:
            _, completed_seconds = self.owner.recorder.log_handler.get_today_stats()
            return completed_seconds
        except Exception as e:
            logger.error("今日の完了プレイ時間のロード中にエラーが発生しました: %s", e)
            return 0.0
