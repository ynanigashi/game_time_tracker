"""SQLite-backed play log store."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import platform
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.infra.play_log_models import (
    PendingPlayLogRecord,
    PlayLogRecord,
    PlayLogWrite,
    deserialize_play_log_bool,
    serialize_play_log_bool,
)
from src.infra.runtime_paths import default_play_log_db_file
from src.infra.sqlite_base_store import SQLiteBaseStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayLogImportResult:
    """Summary of play-log rows imported from an external source."""

    imported: int
    skipped: int


class PlayLogStore(SQLiteBaseStore):
    """Persist play session logs locally in SQLite."""

    SCHEMA_VERSION = 3
    SCHEMA_STATEMENTS = (
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
            sync_action TEXT NOT NULL DEFAULT 'append',
            deleted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    INDEX_STATEMENTS = (
        """
        CREATE INDEX IF NOT EXISTS idx_play_records_index
        ON play_records(record_index)
        """,
    )
    LEGACY_COLUMN_STATEMENTS = {
        "sync_action": """
            ALTER TABLE play_records
            ADD COLUMN sync_action TEXT NOT NULL DEFAULT 'append'
        """,
        "deleted": """
            ALTER TABLE play_records
            ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0
        """,
    }

    def __init__(
        self,
        db_path: Optional[Path] = None,
        *,
        device_id: Optional[str] = None,
    ) -> None:
        super().__init__(db_path or default_play_log_db_file())
        self.device_id = device_id or self._default_device_id()

    @staticmethod
    def _default_device_id() -> str:
        return (
            os.environ.get("COMPUTERNAME")
            or platform.node()
            or "unknown-device"
        )

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        if self._table_exists(conn, "play_records"):
            columns = self._table_columns(conn, "play_records")
            if "record_id" not in columns:
                self._migrate_legacy_schema(conn)
                return
            self._add_missing_columns(
                conn,
                "play_records",
                self.LEGACY_COLUMN_STATEMENTS,
            )
        super()._ensure_schema(conn)

    def _migrate_legacy_schema(self, conn: sqlite3.Connection) -> None:
        device_id = self.device_id
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
                sync_action TEXT NOT NULL DEFAULT 'append',
                deleted INTEGER NOT NULL DEFAULT 0,
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
                sync_action,
                deleted,
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
                'append',
                0,
                created_at,
                updated_at
            FROM play_records
            """,
            (device_id, device_id),
        )
        conn.execute("DROP TABLE play_records")
        conn.execute("ALTER TABLE play_records_new RENAME TO play_records")
        self._execute_statements(conn, self.INDEX_STATEMENTS)

    @staticmethod
    def _serialize_bool(value: Any) -> str:
        return serialize_play_log_bool(value)

    @staticmethod
    def _deserialize_bool(value: Any) -> bool:
        return deserialize_play_log_bool(value)

    @classmethod
    def _row_to_record_model(cls, row: sqlite3.Row) -> PlayLogRecord:
        return PlayLogRecord(
            record_id=str(row["record_id"]),
            device_id=str(row["device_id"]),
            index=int(row["record_index"]),
            start_time=str(row["start_time"]),
            end_time=str(row["end_time"]),
            title=str(row["title"]),
            play_with_friends=cls._deserialize_bool(row["play_with_friends"]),
        )

    @classmethod
    def _row_to_pending_record_model(cls, row: sqlite3.Row) -> PendingPlayLogRecord:
        return PendingPlayLogRecord(
            record=cls._row_to_record_model(row),
            sync_action=str(row["sync_action"]),
        )

    @classmethod
    def _row_to_record(cls, row: sqlite3.Row) -> Dict[str, Any]:
        return cls._row_to_record_model(row).to_dict()

    @classmethod
    def _row_to_pending_record(cls, row: sqlite3.Row) -> Dict[str, Any]:
        return cls._row_to_pending_record_model(row).to_dict()

    def load_record_models(self) -> List[PlayLogRecord]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT record_id, device_id, record_index, start_time, end_time,
                       title, play_with_friends
                FROM play_records
                WHERE deleted = 0
                ORDER BY record_index
                """
            ).fetchall()
        return [self._row_to_record_model(row) for row in rows]

    def load_records(self) -> List[Dict[str, Any]]:
        return [record.to_dict() for record in self.load_record_models()]

    def max_index(self) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(record_index), 0) FROM play_records"
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def save_record_model(
        self,
        write: PlayLogWrite,
        *,
        backed_up: bool = False,
    ) -> PlayLogRecord:
        record = PlayLogRecord.from_write(
            write,
            record_id=str(uuid4()),
            device_id=self.device_id,
        )
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
                    sync_action,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(record_id) DO UPDATE SET
                    device_id = excluded.device_id,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    title = excluded.title,
                    play_with_friends = excluded.play_with_friends,
                    backed_up = excluded.backed_up,
                    sync_action = excluded.sync_action,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    record.record_id,
                    record.device_id,
                    record.index,
                    record.start_time,
                    record.end_time,
                    record.title,
                    self._serialize_bool(record.play_with_friends),
                    1 if backed_up else 0,
                    "append",
                ),
            )
        return record

    def save_record(
        self,
        values: List[Any],
        *,
        backed_up: bool = False,
    ) -> Dict[str, Any]:
        return self.save_record_model(
            PlayLogWrite.from_values(values),
            backed_up=backed_up,
        ).to_dict()

    def import_records(self, records: List[Dict[str, Any]], *, backed_up: bool) -> int:
        return self.import_records_detailed(records, backed_up=backed_up).imported

    def import_records_detailed(
        self,
        records: List[Dict[str, Any]],
        *,
        backed_up: bool,
    ) -> PlayLogImportResult:
        imported = 0
        skipped = 0
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
                    skipped += 1
                    continue
                imported += 1
        return PlayLogImportResult(imported=imported, skipped=skipped)

    def _normalize_imported_record(self, record: Dict[str, Any]) -> PlayLogRecord:
        return PlayLogRecord.from_mapping(record)

    @staticmethod
    def _upsert_imported_record(
        conn: sqlite3.Connection,
        normalized: PlayLogRecord,
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
                sync_action,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(record_id) DO UPDATE SET
                device_id = excluded.device_id,
                record_index = excluded.record_index,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                title = excluded.title,
                play_with_friends = excluded.play_with_friends,
                backed_up = excluded.backed_up,
                sync_action = excluded.sync_action,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                normalized.record_id,
                normalized.device_id,
                normalized.index,
                normalized.start_time,
                normalized.end_time,
                normalized.title,
                serialize_play_log_bool(normalized.play_with_friends),
                1 if backed_up else 0,
                "append",
            ),
        )

    def save_imported_record_model(
        self,
        record: Dict[str, Any],
        *,
        backed_up: bool,
    ) -> PlayLogRecord:
        normalized = self._normalize_imported_record(record)
        with self._connection() as conn:
            self._upsert_imported_record(conn, normalized, backed_up=backed_up)
        return normalized

    def save_imported_record(
        self,
        record: Dict[str, Any],
        *,
        backed_up: bool,
    ) -> Dict[str, Any]:
        return self.save_imported_record_model(
            record,
            backed_up=backed_up,
        ).to_dict()

    def mark_backed_up(self, record_id: str) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE play_records
                SET backed_up = 1,
                    sync_action = 'append',
                    updated_at = CURRENT_TIMESTAMP
                WHERE record_id = ?
                """,
                (record_id,),
            )

    def reissue_record_id_model(self, record_id: str) -> PlayLogRecord:
        new_record_id = str(uuid4())
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE play_records
                SET record_id = ?,
                    backed_up = 0,
                    sync_action = 'append',
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
        return self._row_to_record_model(row)

    def reissue_record_id(self, record_id: str) -> Dict[str, Any]:
        return self.reissue_record_id_model(record_id).to_dict()

    def load_pending_backup_record_models(self) -> List[PendingPlayLogRecord]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT record_id, device_id, record_index, start_time, end_time,
                       title, play_with_friends, sync_action
                FROM play_records
                WHERE backed_up = 0
                ORDER BY record_index
                """
            ).fetchall()
        return [self._row_to_pending_record_model(row) for row in rows]

    def load_pending_backup_records(self) -> List[Dict[str, Any]]:
        return [
            record.to_dict()
            for record in self.load_pending_backup_record_models()
        ]

    def update_record_model(
        self,
        record_id: str,
        write: PlayLogWrite,
        *,
        backed_up: bool = False,
        sync_action: str = "update",
    ) -> PlayLogRecord:
        if sync_action not in {"append", "update"}:
            raise ValueError(f"unknown play log sync action: {sync_action}")

        with self._connection() as conn:
            conn.execute(
                """
                UPDATE play_records
                SET record_index = ?,
                    start_time = ?,
                    end_time = ?,
                    title = ?,
                    play_with_friends = ?,
                    backed_up = ?,
                    sync_action = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE record_id = ?
                """,
                (
                    write.index,
                    write.start_time,
                    write.end_time,
                    write.title,
                    write.serialized_friends(),
                    1 if backed_up else 0,
                    "append" if backed_up else sync_action,
                    record_id,
                ),
            )
            row = conn.execute(
                """
                SELECT record_id, device_id, record_index, start_time, end_time,
                       title, play_with_friends
                FROM play_records
                WHERE record_id = ?
                """,
                (record_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"play record not found: {record_id}")
        return self._row_to_record_model(row)

    def update_record(
        self,
        record_id: str,
        values: List[Any],
        *,
        backed_up: bool = False,
        sync_action: str = "update",
    ) -> Dict[str, Any]:
        return self.update_record_model(
            record_id,
            PlayLogWrite.from_values(values),
            backed_up=backed_up,
            sync_action=sync_action,
        ).to_dict()

    def delete_record_model(self, record_id: str) -> PlayLogRecord:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT record_id, device_id, record_index, start_time, end_time,
                       title, play_with_friends, backed_up, sync_action
                FROM play_records
                WHERE record_id = ?
                """,
                (record_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"play record not found: {record_id}")

            record = self._row_to_record_model(row)
            if int(row["backed_up"]) == 0 and str(row["sync_action"]) == "append":
                conn.execute(
                    "DELETE FROM play_records WHERE record_id = ?",
                    (record_id,),
                )
                return record

            conn.execute(
                """
                UPDATE play_records
                SET deleted = 1,
                    backed_up = 0,
                    sync_action = 'delete',
                    updated_at = CURRENT_TIMESTAMP
                WHERE record_id = ?
                """,
                (record_id,),
            )
        return record

    def delete_record(self, record_id: str) -> Dict[str, Any]:
        return self.delete_record_model(record_id).to_dict()
