"""Editable application config helpers."""

import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.infra.config_loader import (
    ConfigLoader,
    DEFAULT_BROWSERS,
    DEFAULT_EXCLUDED_TITLES,
)
from src.infra.runtime_paths import resolve_config_file
from src.infra.settings_store import SettingsStore


@dataclass
class EditableAppConfig:
    """Config values exposed in the settings UI."""

    json_file_path: str
    log_sheet_key: str
    game_info_sheet_key: str
    game_info_sheet_gid: int
    browsers: list[str]
    excluded_titles: list[str]


def _split_lines_or_commas(value: str) -> list[str]:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    items: list[str] = []
    for line in normalized.split("\n"):
        items.extend(part.strip() for part in line.split(",") if part.strip())
    return items


def parse_list_text(value: str, default: list[str]) -> list[str]:
    items = _split_lines_or_commas(value)
    return items if items else list(default)


def list_to_text(values: list[str]) -> str:
    return "\n".join(values)


def _typed_config_to_editable(loader: ConfigLoader) -> EditableAppConfig:
    config = loader.load()
    return EditableAppConfig(
        json_file_path=config.log_handler.cert_file_path,
        log_sheet_key=config.log_handler.sheet_key,
        game_info_sheet_key=config.game_info.sheet_key,
        game_info_sheet_gid=config.game_info.sheet_gid,
        browsers=list(config.window_scan.browsers),
        excluded_titles=list(config.window_scan.excluded_titles),
    )


def load_editable_config(
    *,
    config_file_path: Optional[str] = None,
    settings_store: Optional[SettingsStore] = None,
) -> EditableAppConfig:
    return _typed_config_to_editable(
        ConfigLoader(
            config_file_path=config_file_path,
            settings_store=settings_store,
        )
    )


def validate_editable_config(config: EditableAppConfig) -> None:
    required = {
        "json_file_path": config.json_file_path,
        "log_sheet_key": config.log_sheet_key,
        "game_info_sheet_key": config.game_info_sheet_key,
    }
    missing = [key for key, value in required.items() if not value.strip()]
    if missing:
        raise ValueError(f"必須項目が未入力です: {', '.join(missing)}")
    if int(config.game_info_sheet_gid) < 0:
        raise ValueError("sheet_gid は0以上の整数で指定してください")


def editable_config_to_parser(config: EditableAppConfig) -> configparser.ConfigParser:
    validate_editable_config(config)
    parser = configparser.ConfigParser()
    parser["LOGHANDLER"] = {
        "json_file_path": config.json_file_path.strip(),
        "sheet_key": config.log_sheet_key.strip(),
    }
    parser["GAMEINFO"] = {
        "sheet_key": config.game_info_sheet_key.strip(),
        "sheet_gid": str(int(config.game_info_sheet_gid)),
    }
    parser["WINDOW_SCAN"] = {
        "browsers": ", ".join(config.browsers or DEFAULT_BROWSERS),
        "exclude_titles": ", ".join(config.excluded_titles or DEFAULT_EXCLUDED_TITLES),
    }
    return parser


def save_editable_config(
    config: EditableAppConfig,
    *,
    settings_store: Optional[SettingsStore] = None,
) -> Path:
    """Save settings to SQLite only."""
    parser = editable_config_to_parser(config)
    store = settings_store or SettingsStore()
    store.save_config(parser)
    return store.db_path


def export_editable_config(
    config: EditableAppConfig,
    *,
    config_file_path: Optional[str] = None,
) -> Path:
    """Export settings to an INI file."""
    parser = editable_config_to_parser(config)
    target_path = Path(config_file_path) if config_file_path else resolve_config_file()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as file:
        parser.write(file)
    return target_path


def import_editable_config(
    config_file_path: str,
    *,
    settings_store: Optional[SettingsStore] = None,
) -> EditableAppConfig:
    """Import an INI file into SQLite and return the imported values."""
    loader = ConfigLoader(config_file_path=config_file_path)
    editable_config = _typed_config_to_editable(loader)
    store = settings_store or SettingsStore()
    store.save_config(editable_config_to_parser(editable_config))
    return editable_config
