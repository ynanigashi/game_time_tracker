import configparser
from typing import List

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

# 設定ファイルの読み込み
class ConfigLoader:
    """設定ファイルを読み込むクラス."""
    
    # 必須の設定キー
    REQUIRED_KEYS = {
        'LOGHANDLER': ['json_file_path', 'sheet_key'],
        'GAMEINFO': ['sheet_key', 'sheet_gid'],
    }

    def __init__(self):
        self.config_file_path = 'config.ini'
        self.config = configparser.ConfigParser()
        self.config.read(self.config_file_path, encoding='utf-8')
        self._validate_required_keys()
        self.load()

    def _validate_required_keys(self) -> None:
        """必須キーの存在を検証。"""
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

    def load(self):
        self.log_handler = {
            'cert_file_path': self.config['LOGHANDLER']['json_file_path'],
            'sheet_key': self.config['LOGHANDLER']['sheet_key'],
        }

        # sheet_gid を int に変換（スプレッドシートAPIはintを期待）
        try:
            sheet_gid = int(self.config['GAMEINFO']['sheet_gid'])
        except ValueError:
            raise ValueError(f"config.ini の [GAMEINFO] sheet_gid は整数である必要があります: {self.config['GAMEINFO']['sheet_gid']}")

        self.game_info = {
            'sheet_key': self.config['GAMEINFO']['sheet_key'],
            'sheet_gid': sheet_gid,
        }

        self.window_scan = {
            'browsers': self._get_list('WINDOW_SCAN', 'browsers', DEFAULT_BROWSERS),
            'excluded_titles': self._get_list('WINDOW_SCAN', 'exclude_titles', DEFAULT_EXCLUDED_TITLES),
        }

    def _get_list(self, section: str, key: str, default: List[str]) -> List[str]:
        if section not in self.config or key not in self.config[section]:
            return list(default)
        raw = self.config.get(section, key, fallback='')
        items = [item.strip() for item in raw.split(',') if item.strip()]
        return items if items else list(default)
