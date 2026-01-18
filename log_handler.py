from datetime import datetime
from pathlib import Path

# https://docs.gspread.org/en/v5.12.1/
import gspread

from config_loader import ConfigLoader

class LogHandler():

    def __init__(self):
        config = ConfigLoader()
        gc = gspread.service_account(filename=Path(config.log_handler['cert_file_path']))
        self.sheet = gc.open_by_key(config.log_handler['sheet_key']).sheet1
        self.records = self.get_all_records()
        self.index = len(self.records)

    def get_all_records(self):
        return self.sheet.get_all_records()

    def get_all_values(self):
        return self.sheet.get_all_values()
    
    def get_and_increment_index(self):
        self.index += 1
        return self.index

    # Backward compatibility for older callers
    def get_and_incremant_index(self):
        return self.get_and_increment_index()
    
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

    def get_cached_records(self):
        """キャッシュされたレコードを返す（スプレッドシートにアクセスしない）."""
        return self.records

    def save_record(self, values) -> bool:
        """レコードをスプレッドシートに保存。
        
        Returns:
            保存成功時True、失敗時False。
        """
        try:
            self.sheet.append_row(values, value_input_option='USER_ENTERED')
            # ローカルキャッシュにも追加（スプレッドシート再読込を避ける）
            if len(values) >= 5:
                self.records.append({
                    'index': values[0],
                    'start_time': values[1],
                    'end_time': values[2],
                    'title': values[3],
                    'play_with_friends': values[4],
                })
            return True
        except gspread.exceptions.APIError as e:
            print(f'APIError occurred while appending row: {e}')
            return False
        except Exception as e:
            print(f'Exception occurred while appending row: {e}')
            return False
            
def main():
    pass

if __name__ == '__main__':
    main()
