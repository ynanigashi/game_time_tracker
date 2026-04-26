"""SQLite-backed play log store."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import os
import platform
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from uuid import uuid4

from src.infra.runtime_paths import default_play_log_db_file

logger = logging.getLogger(__name__)


class PlayLogStore:
    """Persist play session logs locally in SQLite."""

    _INDEX_KEYS = ("index", "record_index", "No", "no")
    _FRIENDS_KEYS = ("play_with_friends", "with_friends")

    def __init__(
        self,
        db_path: Optional[Path] = None,
        *,
        device_id: Optional[str] = None,
    ) -> None:
        self.db_path = db_path or default_play_log_db_file()
        self.device_id = device_id or self._default_device_id()

    @staticmethod
    def _default_device_id() -> str:
        return (
            os.environ.get("COMPUTERNAME")
            or platform.node()
            or "unknown-device"
        )

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self._ensure_schema(conn)
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='play_records'"
        ).fetchone()
        if existing is not None:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(play_records)").fetchall()
            }
            if "record_id" not in columns:
                PlayLogStore._migrate_legacy_schema(conn)
                return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS play_records (
                record_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                record_index INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                title TEXT NOT NULL,
                play_with_friends TEXT NOT NULL,
                backed_up INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_play_records_index
            ON play_records(record_index)
            """
        )

    @staticmethod
    def _migrate_legacy_schema(conn: sqlite3.Connection) -> None:
        device_id = PlayLogStore._default_device_id()
        conn.execute(
            """
            CREATE TABLE play_records_new (
                record_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                record_index INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                title TEXT NOT NULL,
                play_with_friends TEXT NOT NULL,
                backed_up INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO play_records_new(
                record_id,
                device_id,
                record_index,
                start_time,
                end_time,
                title,
                play_with_friends,
                backed_up,
                created_at,
                updated_at
            )
            SELECT
                ? || ':' || record_index,
                ?,
                record_index,
                start_time,
                end_time,
                title,
                play_with_friends,
                backed_up,
                created_at,
                updated_at
            FROM play_records
            """,
            (device_id, device_id),
        )
        conn.execute("DROP TABLE play_records")
        conn.execute("ALTER TABLE play_records_new RENAME TO play_records")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_play_records_index
            ON play_records(record_index)
            """
        )

    @staticmethod
    def _serialize_bool(value: Any) -> str:
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        return "TRUE" if str(value).upper() == "TRUE" else "FALSE"

    @staticmethod
    def _deserialize_bool(value: Any) -> bool:
        return str(value).upper() == "TRUE"

    @classmethod
    def _row_to_record(cls, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "record_id": row["record_id"],
            "device_id": row["device_id"],
            "index": row["record_index"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "title": row["title"],
            "play_with_friends": cls._deserialize_bool(row["play_with_friends"]),
        }

    @staticmethod
    def _first_present(
        record: Dict[str, Any],
        keys: tuple[str, ...],
        default: Any = "",
    ) -> Any:
        for key in keys:
            value = record.get(key)
            if value not in (None, ""):
                return value
        return default

    def _record_index_from(self, record: Dict[str, Any]) -> int:
        index = self._first_present(record, self._INDEX_KEYS)
        if index in (None, ""):
            raise ValueError("play record index is required")
        return int(index)

    def _record_id_from(self, record: Dict[str, Any]) -> str:
        record_id = str(record.get("record_id") or record.get("id") or "").strip()
        if record_id:
            return record_id
        record_index = self._record_index_from(record)
        return f"sheet:{record_index}"

    def load_records(self) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT record_id, device_id, record_index, start_time, end_time,
                       title, play_with_friends
                FROM play_records
                ORDER BY record_index
                """
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def max_index(self) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(record_index), 0) FROM play_records"
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def save_record(
        self,
        values: List[Any],
        *,
        backed_up: bool = False,
    ) -> Dict[str, Any]:
        if len(values) < 5:
            raise ValueError("play record requires index, start, end, title, friends")

        record = {
            "record_id": str(uuid4()),
            "device_id": self.device_id,
            "index": int(values[0]),
            "start_time": str(values[1]),
            "end_time": str(values[2]),
            "title": str(values[3]),
            "play_with_friends": self._serialize_bool(values[4]),
        }
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO play_records(
                    record_id,
                    device_id,
                    record_index,
                    start_time,
                    end_time,
                    title,
                    play_with_friends,
                    backed_up,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(record_id) DO UPDATE SET
                    device_id = excluded.device_id,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    title = excluded.title,
                    play_with_friends = excluded.play_with_friends,
                    backed_up = excluded.backed_up,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    record["record_id"],
                    record["device_id"],
                    record["index"],
                    record["start_time"],
                    record["end_time"],
                    record["title"],
                    record["play_with_friends"],
                    1 if backed_up else 0,
                ),
            )
        return {
            **record,
            "play_with_friends": self._deserialize_bool(record["play_with_friends"]),
        }

    def import_records(self, records: List[Dict[str, Any]], *, backed_up: bool) -> int:
        imported = 0
        with self._connection() as conn:
            for record in records:
                try:
                    normalized = self._normalize_imported_record(record)
                    self._upsert_imported_record(
                        conn,
                        normalized,
                        backed_up=backed_up,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    logger.debug("skipped invalid play record during import: %s", exc)
                    continue
                imported += 1
        return imported

    def _normalize_imported_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        record_id = self._record_id_from(record)
        return {
            "record_id": record_id,
            "device_id": str(record.get("device_id") or "unknown-device"),
            "index": self._record_index_from(record),
            "start_time": str(record["start_time"]),
            "end_time": str(record["end_time"]),
            "title": str(record["title"]),
            "play_with_friends": self._serialize_bool(
                self._first_present(record, self._FRIENDS_KEYS, False)
            ),
        }

    @staticmethod
    def _upsert_imported_record(
        conn: sqlite3.Connection,
        normalized: Dict[str, Any],
        *,
        backed_up: bool,
    ) -> None:
        conn.execute(
            """
            INSERT INTO play_records(
                record_id,
                device_id,
                record_index,
                start_time,
                end_time,
                title,
                play_with_friends,
                backed_up,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(record_id) DO UPDATE SET
                device_id = excluded.device_id,
                record_index = excluded.record_index,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                title = excluded.title,
                play_with_friends = excluded.play_with_friends,
                backed_up = excluded.backed_up,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                normalized["record_id"],
                normalized["device_id"],
                normalized["index"],
                normalized["start_time"],
                normalized["end_time"],
                normalized["title"],
                normalized["play_with_friends"],
                1 if backed_up else 0,
            ),
        )

    def save_imported_record(
        self,
        record: Dict[str, Any],
        *,
        backed_up: bool,
    ) -> Dict[str, Any]:
        normalized = self._normalize_imported_record(record)
        with self._connection() as conn:
            self._upsert_imported_record(conn, normalized, backed_up=backed_up)
        return {
            **normalized,
            "play_with_friends": self._deserialize_bool(
                normalized["play_with_friends"]
            ),
        }

    def mark_backed_up(self, record_id: str) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE play_records
                SET backed_up = 1, updated_at = CURRENT_TIMESTAMP
                WHERE record_id = ?
                """,
                (record_id,),
            )

    def reissue_record_id(self, record_id: str) -> Dict[str, Any]:
        new_record_id = str(uuid4())
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE play_records
                SET record_id = ?,
                    backed_up = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE record_id = ?
                """,
                (new_record_id, record_id),
            )
            row = conn.execute(
                """
                SELECT record_id, device_id, record_index, start_time, end_time,
                       title, play_with_friends
                FROM play_records
                WHERE record_id = ?
                """,
                (new_record_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"play record not found: {record_id}")
        return self._row_to_record(row)

    def load_pending_backup_records(self) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT record_id, device_id, record_index, start_time, end_time,
                       title, play_with_friends
                FROM play_records
                WHERE backed_up = 0
                ORDER BY record_index
                """
            ).fetchall()
        return [self._row_to_record(row) for row in rows]
