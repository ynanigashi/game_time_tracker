import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.infra.runtime_paths import default_config_file, resolve_config_file
from src.infra.settings_store import SettingsStore


DEFAULT_CONFIG_FILE = str(default_config_file())

DEFAULT_BROWSERS = [
    "Google Chrome",
    "Microsoft Edge",
    "Mozilla Firefox",
    "Opera",
    "Brave",
    "Vivaldi",
    "Safari",
]

DEFAULT_EXCLUDED_TITLES = [
    "Program Manager",
    "Settings",
    "設定",
    "NVIDIA GeForce Overlay",
    "Windows 入力エクスペリエンス",
    "Microsoft Store",
    "game_time_tracker.bat",
    "Nahimic",
]

PLAY_LOG_BACKUP_MODE_LOCAL_ONLY = "local_only"
PLAY_LOG_BACKUP_MODE_SPREADSHEET = "spreadsheet"
PLAY_LOG_BACKUP_MODES = {
    PLAY_LOG_BACKUP_MODE_LOCAL_ONLY,
    PLAY_LOG_BACKUP_MODE_SPREADSHEET,
}
PLAY_LOG_SYNC_CONFLICT_OVERWRITE = "overwrite"
PLAY_LOG_SYNC_CONFLICT_NEW_ID = "new_id"
PLAY_LOG_SYNC_CONFLICT_POLICIES = {
    PLAY_LOG_SYNC_CONFLICT_OVERWRITE,
    PLAY_LOG_SYNC_CONFLICT_NEW_ID,
}


class ConfigNotConfiguredError(KeyError):
    """Raised when required application settings are missing."""


@dataclass
class LogHandlerConfig:
    """Play log handler settings."""

    cert_file_path: str
    sheet_key: str
    backup_mode: str = PLAY_LOG_BACKUP_MODE_SPREADSHEET
    sheet_gid: Optional[int] = None
    sync_conflict_policy: str = PLAY_LOG_SYNC_CONFLICT_OVERWRITE


@dataclass
class GameInfoConfig:
    """Game info spreadsheet settings."""

    sheet_key: str
    sheet_gid: int


@dataclass
class WindowScanConfig:
    """Window scanning settings."""

    browsers: List[str]
    excluded_titles: List[str]


@dataclass
class Config:
    """Application settings."""

    log_handler: LogHandlerConfig
    game_info: GameInfoConfig
    window_scan: WindowScanConfig


class ConfigLoader:
    """Load application settings from SQLite, with config.ini as migration input."""

    REQUIRED_KEYS = {
        "LOGHANDLER": ["json_file_path"],
        "GAMEINFO": ["sheet_key", "sheet_gid"],
    }

    def __init__(
        self,
        config_file_path: Optional[str] = None,
        settings_store: Optional[SettingsStore] = None,
    ):
        self.config = configparser.ConfigParser()
        if config_file_path is None:
            self.config_file_path = str(resolve_config_file())
            self.settings_store = settings_store or SettingsStore()
            config_path = Path(self.config_file_path)
            stored_config = self.settings_store.load_config()
            if self._has_required_keys(stored_config):
                self.config = stored_config
            elif config_path.exists():
                self.config = self.settings_store.import_config_file(config_path)
            else:
                self.config = stored_config
        else:
            self.config_file_path = config_file_path
            self.settings_store = settings_store
            self.config.read(self.config_file_path, encoding="utf-8")
        self._validate_required_keys()

    @classmethod
    def _has_required_keys(cls, config: configparser.ConfigParser) -> bool:
        for section, keys in cls.REQUIRED_KEYS.items():
            if section not in config:
                return False
            for key in keys:
                if key not in config[section]:
                    return False
        backup_mode = cls._get_backup_mode(config)
        if backup_mode == PLAY_LOG_BACKUP_MODE_SPREADSHEET:
            return "sheet_key" in config["LOGHANDLER"]
        return True

    @staticmethod
    def _get_backup_mode(config: configparser.ConfigParser) -> str:
        if "LOGHANDLER" not in config:
            return PLAY_LOG_BACKUP_MODE_SPREADSHEET
        raw = config["LOGHANDLER"].get(
            "backup_mode",
            PLAY_LOG_BACKUP_MODE_SPREADSHEET,
        )
        return (raw or PLAY_LOG_BACKUP_MODE_SPREADSHEET).strip()

    def _validate_required_keys(self) -> None:
        """Validate that all required config keys are present."""
        missing = []
        for section, keys in self.REQUIRED_KEYS.items():
            if section not in self.config:
                missing.append(f"section [{section}]")
            else:
                for key in keys:
                    if key not in self.config[section]:
                        missing.append(f"[{section}] {key}")
        backup_mode = self._get_backup_mode(self.config)
        if backup_mode not in PLAY_LOG_BACKUP_MODES:
            raise ValueError(
                "[LOGHANDLER] backup_mode は "
                f"{PLAY_LOG_BACKUP_MODE_LOCAL_ONLY} または "
                f"{PLAY_LOG_BACKUP_MODE_SPREADSHEET} を指定してください: "
                f"{backup_mode}"
            )
        sync_conflict_policy = self._get_sync_conflict_policy(self.config)
        if sync_conflict_policy not in PLAY_LOG_SYNC_CONFLICT_POLICIES:
            raise ValueError(
                "[LOGHANDLER] sync_conflict_policy は "
                f"{PLAY_LOG_SYNC_CONFLICT_OVERWRITE} または "
                f"{PLAY_LOG_SYNC_CONFLICT_NEW_ID} を指定してください: "
                f"{sync_conflict_policy}"
            )
        if (
            backup_mode == PLAY_LOG_BACKUP_MODE_SPREADSHEET
            and "LOGHANDLER" in self.config
            and "sheet_key" not in self.config["LOGHANDLER"]
        ):
            missing.append("[LOGHANDLER] sheet_key")
        if missing:
            raise ConfigNotConfiguredError(
                f"config.ini is missing required settings: {', '.join(missing)}"
            )

    def load(self) -> Config:
        """Return typed application settings."""
        log_sheet_gid = self._get_optional_int("LOGHANDLER", "sheet_gid")
        log_handler = LogHandlerConfig(
            cert_file_path=self.config["LOGHANDLER"]["json_file_path"],
            sheet_key=self.config["LOGHANDLER"].get("sheet_key", ""),
            backup_mode=self._get_backup_mode(self.config),
            sheet_gid=log_sheet_gid,
            sync_conflict_policy=self._get_sync_conflict_policy(self.config),
        )

        try:
            sheet_gid = int(self.config["GAMEINFO"]["sheet_gid"])
        except ValueError:
            configured_sheet_gid = self.config["GAMEINFO"]["sheet_gid"]
            raise ValueError(
                "config.ini の [GAMEINFO] sheet_gid は整数である必要があります: "
                f"{configured_sheet_gid}"
            )

        game_info = GameInfoConfig(
            sheet_key=self.config["GAMEINFO"]["sheet_key"],
            sheet_gid=sheet_gid,
        )

        window_scan = WindowScanConfig(
            browsers=self._get_list("WINDOW_SCAN", "browsers", DEFAULT_BROWSERS),
            excluded_titles=self._get_list(
                "WINDOW_SCAN",
                "exclude_titles",
                DEFAULT_EXCLUDED_TITLES,
            ),
        )

        return Config(
            log_handler=log_handler,
            game_info=game_info,
            window_scan=window_scan,
        )

    def _get_optional_int(self, section: str, key: str) -> Optional[int]:
        raw = self.config.get(section, key, fallback="").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            raise ValueError(
                f"config.ini の [{section}] {key} は整数である必要があります: {raw}"
            )

    @staticmethod
    def _get_sync_conflict_policy(config: configparser.ConfigParser) -> str:
        if "LOGHANDLER" not in config:
            return PLAY_LOG_SYNC_CONFLICT_OVERWRITE
        raw = config["LOGHANDLER"].get(
            "sync_conflict_policy",
            PLAY_LOG_SYNC_CONFLICT_OVERWRITE,
        )
        return (raw or PLAY_LOG_SYNC_CONFLICT_OVERWRITE).strip()

    def _get_list(self, section: str, key: str, default: List[str]) -> List[str]:
        if section not in self.config or key not in self.config[section]:
            return list(default)
        raw = self.config.get(section, key, fallback="")
        items = [item.strip() for item in raw.split(",") if item.strip()]
        return items if items else list(default)
