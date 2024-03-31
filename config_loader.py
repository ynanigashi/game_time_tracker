import configparser

# 設定ファイルの読み込み
class ConfigLoader:
    def __init__(self):
        self.config_file_path = 'config.ini'
        self.config = configparser.ConfigParser()
        self.config.read(self.config_file_path, encoding='utf-8')
        self.load()

    def load(self):
        self.application_manager = {
            'use_spreadsheet': self.config.getboolean('APPLICATIONMANAGER', 'use_spreadsheet'),
        }

        self.game_timer = {
            'limit_seconds': int(self.config['GAMETIMER']['limit_minutes']) * 60,
            'json_file_path': self.config['GAMETIMER']['json_file_path'],
        }

        self.log_handler = {
            'cert_file_path': self.config['LOGHANDLER']['json_file_path'],
            'sheet_key': self.config['LOGHANDLER']['sheet_key'],
        }

        self.game_info = {
            'sheet_key': self.config['GAMEINFO']['sheet_key'],
            'sheet_gid': self.config['GAMEINFO']['sheet_gid'],
        }
