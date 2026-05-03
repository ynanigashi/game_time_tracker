"""Shared SQLite store primitives."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


class SQLiteBaseStore(ABC):
    """Base class for SQLite-backed stores with per-store schemas."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            self._configure_connection(conn)
            conn.execute("BEGIN EXCLUSIVE")
            self._ensure_schema(conn)
            self._migrate_schema_version(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            conn.close()
            raise
        return conn

    def _configure_connection(self, conn: sqlite3.Connection) -> None:
        """Apply optional per-store connection settings."""

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @abstractmethod
    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Create or migrate the store schema."""

    def _migrate_schema_version(self, conn: sqlite3.Connection) -> None:
        """Run versioned migrations and update PRAGMA user_version."""
        current_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        target_version = int(self.SCHEMA_VERSION)
        if current_version > target_version:
            raise RuntimeError(
                f"{self.__class__.__name__} DB schema version "
                f"{current_version} is newer than supported {target_version}"
            )
        if current_version < target_version:
            self._migrate(conn, current_version, target_version)
            conn.execute(f"PRAGMA user_version = {target_version}")

    def _migrate(
        self,
        conn: sqlite3.Connection,
        from_version: int,
        to_version: int,
    ) -> None:
        """Hook for per-store schema migrations after _ensure_schema()."""
