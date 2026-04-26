import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.infra.runtime_paths import default_config_file, resolve_config_file
from src.infra.settings_store import SettingsStore


DEFAULT_CONFIG_FILE = str(default_config_file())

DEFAULT_BROWSERS = [
    'Google Chrome',
    'Microsoft Edge',
    'Mozilla Firefox',
    'Opera',
    'Brave',
    'Vivaldi',
    'Safari',
]

DEFAULT_EXCLUDED_TITLES = [
    'Program Manager',
    'Settings',
    '設定',
    'NVIDIA GeForce Overlay',
    'Windows 入力エクスペリエンス',
    'Microsoft Store',
    'game_time_tracker.bat',
    'Nahimic',
]


@dataclass
class LogHandlerConfig:
    """ログハンドラー設定."""

    cert_file_path: str
    sheet_key: str


@dataclass
class GameInfoConfig:
    """ゲーム情報設定."""

    sheet_key: str
    sheet_gid: int


@dataclass
class WindowScanConfig:
    """ウィンドウスキャン設定."""

    browsers: List[str]
    excluded_titles: List[str]


@dataclass
class Config:
    """アプリケーション設定."""

    log_handler: LogHandlerConfig
    game_info: GameInfoConfig
    window_scan: WindowScanConfig


class ConfigLoader:
    """設定ファイルを読み込むクラス."""

    REQUIRED_KEYS = {
        'LOGHANDLER': ['json_file_path', 'sheet_key'],
        'GAMEINFO': ['sheet_key', 'sheet_gid'],
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
            if config_path.exists():
                self.config = self.settings_store.import_config_file(config_path)
            else:
                self.config = self.settings_store.load_config()
        else:
            self.config_file_path = config_file_path
            self.settings_store = settings_store
            self.config.read(self.config_file_path, encoding='utf-8')
        self._validate_required_keys()

    def _validate_required_keys(self) -> None:
        """必須キーの存在を検証する."""
        missing = []
        for section, keys in self.REQUIRED_KEYS.items():
            if section not in self.config:
                missing.append(f'セクション [{section}]')
            else:
                for key in keys:
                    if key not in self.config[section]:
                        missing.append(f'[{section}] の {key}')
        if missing:
            raise KeyError(f"config.ini に必須項目がありません: {', '.join(missing)}")

    def load(self) -> Config:
        """設定を読み込んで Config オブジェクトを返す."""
        log_handler = LogHandlerConfig(
            cert_file_path=self.config['LOGHANDLER']['json_file_path'],
            sheet_key=self.config['LOGHANDLER']['sheet_key'],
        )

        try:
            sheet_gid = int(self.config['GAMEINFO']['sheet_gid'])
        except ValueError:
            configured_sheet_gid = self.config['GAMEINFO']['sheet_gid']
            raise ValueError(
                "config.ini の [GAMEINFO] sheet_gid は整数である必要があります: "
                f"{configured_sheet_gid}"
            )

        game_info = GameInfoConfig(
            sheet_key=self.config['GAMEINFO']['sheet_key'],
            sheet_gid=sheet_gid,
        )

        window_scan = WindowScanConfig(
            browsers=self._get_list('WINDOW_SCAN', 'browsers', DEFAULT_BROWSERS),
            excluded_titles=self._get_list(
                'WINDOW_SCAN', 'exclude_titles', DEFAULT_EXCLUDED_TITLES),
        )

        return Config(
            log_handler=log_handler,
            game_info=game_info,
            window_scan=window_scan,
        )

    def _get_list(self, section: str, key: str, default: List[str]) -> List[str]:
        if section not in self.config or key not in self.config[section]:
            return list(default)
        raw = self.config.get(section, key, fallback='')
        items = [item.strip() for item in raw.split(',') if item.strip()]
        return items if items else list(default)
