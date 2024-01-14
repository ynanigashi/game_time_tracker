# https://docs.gspread.org/en/v5.12.1/
import gspread

from config_loader import ConfigLoader

class LogHandler():

    def __init__(self):
        config = ConfigLoader()
        gc = gspread.service_account(filename=config.log_handler['cert_file_path'])
        self.sheet = gc.open_by_key(config.log_handler['sheet_key']).sheet1

    def get_all_records(self):
        return self.sheet.get_all_records()

    def get_all_values(self):
        return self.sheet.get_all_values()
    
    def save_record(self, values):
        try:
            self.sheet.append_row(values, value_input_option='USER_ENTERED')
        except gspread.exceptions.APIError as e:
            print(f'APIError occurred while appending row: {e}')
        except Exception as e:
            print(f'Exception occurred while appending row: {e}')
            
def main():
    pass


if __name__ == '__main__':
    main()