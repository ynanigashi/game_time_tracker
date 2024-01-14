import configparser

# 設定ファイルの読み込み
class ConfigLoader:
    def __init__(self):
        self.config_file_path = 'config.ini'
        self.config = configparser.ConfigParser()
        self.config.read(self.config_file_path, encoding='utf-8')
        self.load()

    def load(self):
        self.game_timer = {
            'limit_seconds': int(self.config['GAMETIMER']['limit_minutes']) * 60,
            'json_file_path': self.config['GAMETIMER']['json_file_path'],
        }
        self.logger = {
            'cert_file_path': self.config['LOGGER']['cert_file_path'],
            'sheet_key': self.config['LOGGER']['sheet_key'],
        }
