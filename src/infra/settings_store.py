"""SQLite-backed runtime settings store."""

import configparser
import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Optional

from src.infra.runtime_paths import default_settings_db_file
from src.infra.sqlite_base_store import SQLiteBaseStore

logger = logging.getLogger(__name__)


class SettingsStore(SQLiteBaseStore):
    """Persist application settings and small state documents in SQLite."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Optional[Path] = None) -> None:
        super().__init__(db_path or default_settings_db_file())

    def _configure_connection(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                section TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (section, key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS json_documents (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def save_config(self, config: configparser.ConfigParser) -> None:
        """Save INI-style config sections into SQLite."""
        with self._connection() as conn:
            for section in config.sections():
                for key, value in config.items(section):
                    conn.execute(
                        """
                        INSERT INTO settings(section, key, value)
                        VALUES (?, ?, ?)
                        ON CONFLICT(section, key) DO UPDATE SET value = excluded.value
                        """,
                        (section, key, value),
                    )

    def load_config(self) -> configparser.ConfigParser:
        """Load INI-style config sections from SQLite."""
        parser = configparser.ConfigParser()
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT section, key, value FROM settings ORDER BY section, key"
            ).fetchall()

        for section, key, value in rows:
            if not parser.has_section(section):
                parser.add_section(section)
            parser.set(section, key, value)
        return parser

    def import_config_file(self, config_file_path: Path) -> configparser.ConfigParser:
        """Read an INI file, save it to SQLite, and return the parsed config."""
        parser = configparser.ConfigParser()
        parser.read(config_file_path, encoding="utf-8")
        self.save_config(parser)
        return parser

    def load_json_document(self, name: str) -> Optional[Dict[str, object]]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value FROM json_documents WHERE name = ?",
                (name,),
            ).fetchone()
        if row is None:
            return None
        try:
            loaded = json.loads(row[0])
        except (TypeError, json.JSONDecodeError, ValueError):
            logger.warning("invalid JSON document in settings DB: %s", name)
            return None
        return loaded if isinstance(loaded, dict) else None

    def save_json_document(self, name: str, value: Dict[str, object]) -> None:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO json_documents(name, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, serialized),
            )

    def load_window_state(self) -> Optional[Dict[str, object]]:
        return self.load_json_document("window_state")

    def save_window_state(self, value: Dict[str, object]) -> None:
        self.save_json_document("window_state", value)

    def migrate_window_state_file(self, state_file: Path) -> None:
        """Import a legacy window state file into SQLite when DB has no state."""
        if self.load_window_state() is not None or not state_file.exists():
            return

        try:
            loaded = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("failed to read legacy window state: %s", exc)
            return
        if not isinstance(loaded, dict):
            return

        self.save_window_state(loaded)
        try:
            state_file.unlink()
        except OSError as exc:
            logger.warning("failed to remove migrated window state file: %s", exc)
