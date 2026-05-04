"""Shared SQLite store primitives."""

from __future__ import annotations

from abc import ABC
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterable, Iterator, Mapping, Set


class SQLiteBaseStore(ABC):
    """Base class for SQLite-backed stores with per-store schemas."""

    SCHEMA_VERSION = 1
    CONNECTION_PRAGMAS: tuple[str, ...] = ()
    SCHEMA_STATEMENTS: tuple[str, ...] = ()
    INDEX_STATEMENTS: tuple[str, ...] = ()

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
        self._execute_statements(conn, self.CONNECTION_PRAGMAS)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Create the current store schema."""
        self._execute_statements(conn, self.SCHEMA_STATEMENTS)
        self._execute_statements(conn, self.INDEX_STATEMENTS)

    @staticmethod
    def _execute_statements(
        conn: sqlite3.Connection,
        statements: Iterable[str],
    ) -> None:
        """Execute schema or pragma statements in order."""
        for statement in statements:
            conn.execute(statement)

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table_name: str) -> Set[str]:
        return {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }

    def _add_missing_columns(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_statements: Mapping[str, str],
    ) -> None:
        """Add columns whose names are absent from the given table."""
        columns = self._table_columns(conn, table_name)
        for column_name, statement in column_statements.items():
            if column_name not in columns:
                conn.execute(statement)

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
        """Run optional per-version migrations after _ensure_schema()."""
        for version in range(from_version, to_version):
            migration = getattr(self, f"_migrate_{version}_to_{version + 1}", None)
            if callable(migration):
                migration(conn)
