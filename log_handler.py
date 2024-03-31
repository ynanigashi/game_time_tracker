from datetime import datetime

# https://docs.gspread.org/en/v5.12.1/
import gspread

from config_loader import ConfigLoader

class LogHandler():

    def __init__(self):
        config = ConfigLoader()
        gc = gspread.service_account(filename=config.log_handler['cert_file_path'])
        self.sheet = gc.open_by_key(config.log_handler['sheet_key']).sheet1
        self.records = self.get_all_records()
        self.index = len(self.records)

    def get_all_records(self):
        return self.sheet.get_all_records()

    def get_all_values(self):
        return self.sheet.get_all_values()
    
    def get_and_incremant_index(self):
        self.index += 1
        return self.index
    
    def get_titles(self):
        records = self.get_all_records()
        return {record['title'] for record in records}
    
    def get_5_titles_of_recently(self):
        return self.get_n_titles_of_recently(5)

    def get_10_titles_of_recently(self):
        return self.get_n_titles_of_recently(10)

    def get_n_titles_of_recently(self, num):
        records = self.get_all_records()
        recent_of_titles = {}
        for record in records:
            title = record['title']
            start_time = self._gss_timestr_to_datetime(record['start_time'])
            if title not in recent_of_titles or recent_of_titles[title] < start_time:
                recent_of_titles[title] = start_time
        
        # 最新のdatetimeを持つレコードだけを残す
        most_recent_records = [record for record in records if self._gss_timestr_to_datetime(record['start_time']) == recent_of_titles[record['title']]]

        # ソートする
        most_recent_records.sort(key=lambda record: record['start_time'], reverse=True)
        
        return most_recent_records[:num]

    def _gss_timestr_to_datetime(self, timestr):
        return datetime.strptime(timestr, '%Y/%m/%d %H:%M:%S')

    def format_datetime_to_gss_style(self, datetime):
        return datetime.strftime("%Y/%m/%d %H:%M:%S")

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