"""SQLite-backed game catalog store."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.core.models import GameEntry, parse_bool
from src.infra.runtime_paths import default_game_catalog_db_file
from src.infra.sqlite_base_store import SQLiteBaseStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameCatalogSyncResult:
    """Summary of a game-catalog spreadsheet pull."""

    received: int
    imported: int
    disabled: int
    total: int


@dataclass(frozen=True)
class GameCatalogPushResult:
    """Summary of a game-catalog spreadsheet push."""

    sent: int
    updated: int
    appended: int
    failed: int
    total: int


class GameCatalogStore(SQLiteBaseStore):
    """Persist editable game definitions locally in SQLite."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Optional[Path] = None) -> None:
        super().__init__(db_path or default_game_catalog_db_file())

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                game_title TEXT NOT NULL,
                window_title TEXT NOT NULL,
                play_with_friends INTEGER NOT NULL DEFAULT 0,
                is_browser_game INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at TEXT
            )
            """
        )

    @staticmethod
    def _bool_to_int(value: Any) -> int:
        if isinstance(value, bool):
            return 1 if value else 0
        return 1 if parse_bool(value) else 0

    @staticmethod
    def _new_id() -> str:
        return str(uuid4())

    @classmethod
    def _row_to_game(cls, row: sqlite3.Row) -> GameEntry:
        return GameEntry(
            game_title=row["game_title"],
            window_title=row["window_title"],
            play_with_friends=bool(row["play_with_friends"]),
            is_browser_game=bool(row["is_browser_game"]),
            game_id=row["id"],
        )

    @staticmethod
    def _record_id(record: Dict[str, Any]) -> str:
        raw_id = str(record.get("id", "")).strip()
        return raw_id or GameCatalogStore._new_id()

    @classmethod
    def _record_to_game(cls, record: Dict[str, Any]) -> GameEntry:
        return GameEntry(
            game_id=cls._record_id(record),
            game_title=str(record["game_title"]),
            window_title=str(record["window_title"]),
            play_with_friends=parse_bool(
                record.get("play_with_friends", "FALSE")
            ),
            is_browser_game=parse_bool(record.get("is_browser_game", "FALSE")),
        )

    @staticmethod
    def game_to_spreadsheet_values(game: GameEntry) -> List[Any]:
        return [
            game.game_id,
            game.game_title,
            game.window_title,
            "TRUE" if game.play_with_friends else "FALSE",
            "TRUE" if game.is_browser_game else "FALSE",
        ]

    def spreadsheet_records(self) -> List[List[Any]]:
        return [
            self.game_to_spreadsheet_values(game)
            for game in self.load_games()
            if game.game_id
        ]

    def has_any_games(self) -> bool:
        with self._connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM games").fetchone()
        return bool(row and row[0])

    def load_games(self, *, include_disabled: bool = False) -> List[GameEntry]:
        where = ["deleted_at IS NULL"]
        if not include_disabled:
            where.append("enabled = 1")
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, game_title, window_title, play_with_friends,
                       is_browser_game
                FROM games
                WHERE {" AND ".join(where)}
                ORDER BY game_title COLLATE NOCASE, window_title COLLATE NOCASE
                """
            ).fetchall()
        return [self._row_to_game(row) for row in rows]

    def save_game(
        self,
        game: GameEntry,
        *,
        enabled: bool = True,
    ) -> GameEntry:
        game_id = game.game_id.strip() if game.game_id else self._new_id()
        game_title = game.game_title.strip()
        window_title = game.window_title.strip()
        if not game_title or not window_title:
            raise ValueError("game_title and window_title are required")

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO games(
                    id,
                    game_title,
                    window_title,
                    play_with_friends,
                    is_browser_game,
                    enabled,
                    updated_at,
                    deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL)
                ON CONFLICT(id) DO UPDATE SET
                    game_title = excluded.game_title,
                    window_title = excluded.window_title,
                    play_with_friends = excluded.play_with_friends,
                    is_browser_game = excluded.is_browser_game,
                    enabled = excluded.enabled,
                    updated_at = CURRENT_TIMESTAMP,
                    deleted_at = NULL
                """,
                (
                    game_id,
                    game_title,
                    window_title,
                    self._bool_to_int(game.play_with_friends),
                    self._bool_to_int(game.is_browser_game),
                    1 if enabled else 0,
                ),
            )

        return GameEntry(
            game_title=game_title,
            window_title=window_title,
            play_with_friends=bool(game.play_with_friends),
            is_browser_game=bool(game.is_browser_game),
            game_id=game_id,
        )

    def delete_game(self, game_id: str) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE games
                SET enabled = 0,
                    deleted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (game_id,),
            )

    def import_records(self, records: List[Dict[str, Any]]) -> int:
        imported = 0
        for record in records:
            try:
                game = self._record_to_game(record)
                self.save_game(game, enabled=True)
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("skipped invalid game catalog record: %s", exc)
                continue
            imported += 1
        return imported

    def disable_games_not_in(self, game_ids: List[str]) -> int:
        """Disable local games whose IDs are not present in the given list."""
        if not game_ids:
            return 0
        placeholders = ",".join("?" for _ in game_ids)
        with self._connection() as conn:
            cursor = conn.execute(
                f"""
                UPDATE games
                SET enabled = 0,
                    deleted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE deleted_at IS NULL
                  AND id NOT IN ({placeholders})
                """,
                tuple(game_ids),
            )
            return int(cursor.rowcount or 0)

    def sync_records_from_spreadsheet(
        self,
        records: List[Dict[str, Any]],
    ) -> GameCatalogSyncResult:
        """Pull spreadsheet game catalog records into the local DB."""
        imported = 0
        game_ids: List[str] = []
        for record in records:
            try:
                game = self._record_to_game(record)
                self.save_game(game, enabled=True)
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("skipped invalid game catalog sync record: %s", exc)
                continue
            imported += 1
            game_ids.append(game.game_id)

        disabled = self.disable_games_not_in(game_ids)
        return GameCatalogSyncResult(
            received=len(records),
            imported=imported,
            disabled=disabled,
            total=len(self.load_games(include_disabled=True)),
        )
