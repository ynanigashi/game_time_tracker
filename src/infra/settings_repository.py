"""Repository for application configuration storage.

SQLite is the runtime source of truth. INI files are used only for explicit
load/export and first-run migration into SQLite.
"""

from __future__ import annotations

import configparser
from pathlib import Path
from typing import Callable, Optional

from src.infra.runtime_paths import resolve_config_file
from src.infra.settings_store import SettingsStore


class SettingsConfigRepository:
    """Coordinate runtime settings storage and INI migration/import."""

    def __init__(
        self,
        *,
        config_file_path: Optional[str] = None,
        settings_store: Optional[SettingsStore] = None,
    ) -> None:
        self.config_file_path = (
            Path(config_file_path)
            if config_file_path is not None
            else resolve_config_file()
        )
        self.settings_store = settings_store

    def load_explicit_file(self) -> configparser.ConfigParser:
        """Load a specific INI file without writing it to SQLite."""
        parser = configparser.ConfigParser()
        parser.read(self.config_file_path, encoding="utf-8")
        return parser

    def load_runtime_config(
        self,
        is_configured: Callable[[configparser.ConfigParser], bool],
    ) -> configparser.ConfigParser:
        """Load runtime config from SQLite, migrating config.ini if needed."""
        store = self.settings_store or SettingsStore()
        stored_config = store.load_config()
        if is_configured(stored_config):
            return stored_config
        if self.config_file_path.exists():
            return store.import_config_file(self.config_file_path)
        return stored_config

    def save_runtime_config(self, config: configparser.ConfigParser) -> Path:
        """Save runtime config to SQLite."""
        store = self.settings_store or SettingsStore()
        store.save_config(config)
        return store.db_path

    def import_config_file(self) -> configparser.ConfigParser:
        """Import an INI file into SQLite and return the imported parser."""
        store = self.settings_store or SettingsStore()
        return store.import_config_file(self.config_file_path)
