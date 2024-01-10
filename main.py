import time
import datetime
import json
import configparser
import os
import threading

import keyboard
import tkinter as tk
from tkinter import messagebox as mbox


def main():
    gt = GameTimer()
    while True:
        print(f'本日の残り時間は{(gt.limit_seconds - gt.elapsed_seconds)//60}分です')
        input('Press Enter to start the timer.')
        clear_console()
        start_time, end_time = gt.timer()
        # print(f'開始時間:{start_time} / 終了時間:{end_time}')

        # google spreadsheetのフォーマットに変換して表示
        formatted_start_time = format_datetime_to_gss_style(start_time)
        formatted_end_time = format_datetime_to_gss_style(end_time)
        print('以下はgoogle spreadsheetのフォーマットに変換した時間')
        print(f'start time:\n{formatted_start_time}')
        print(f'end time:\n{formatted_end_time}')

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

# 使用例
clear_console()
# datetimeをgoogle spreadsheetのフォーマットに変換
def format_datetime_to_gss_style(datetime):
    return datetime.strftime("%Y/%m/%d %H:%M:%S")



# 設定ファイルの読み込み
class ConfigLoader:
    def __init__(self):
        self.config_file_path = 'config.ini'
        self.config = configparser.ConfigParser()
        self.config.read(self.config_file_path, encoding='utf-8')
        self.load()

    def load(self):
        self.limit_seconds = int(self.config['GAMETIMER']['limit_minutes']) * 60
        self.json_file_path = self.config['GAMETIMER']['json_file_path']


# タイマー関連の処理
class GameTimer():
    
    def __init__(self):
        # 設定ファイルの読み込み
        config = ConfigLoader()
        
        # プレイ可能時間の読み込み
        self.limit_seconds = config.limit_seconds
        
        # 前回以前の経過時間を取得
        self.json_file_path = config.json_file_path
        self.elapsed_seconds = self._get_elapsed_seconds()

        # メッセージボックスを表示するかどうかのフラグ
        self.half_msg_flag = False
        self.end_msg_flag = False
    
    # get elapsed minutes from json file
    def _get_elapsed_seconds(self):
        try:
            with open(self.json_file_path, 'r') as f:
                json_data = json.load(f)
                start_time = datetime.datetime.fromisoformat(json_data['start_time'])
                # 日付が変わっていたら経過時間をリセット
                if start_time.date() != datetime.datetime.now().date():
                    elapsed_seconds = 0
                else:
                    elapsed_seconds = json_data['elasped_seconds']

        except (FileNotFoundError, KeyError):
            elapsed_seconds = 0
        
        return elapsed_seconds


    def timer(self):
        # プレイ時間の計測
        start_time, end_time = self._get_start_and_end_time()
        
        # 経過時間を加算
        self.elapsed_seconds += (end_time - start_time).total_seconds()

        # 経過時間を保存
        self._seve_elapsed_seconds(start_time)

        return start_time, end_time

    def _seve_elapsed_seconds(self, start_time):
        # 開始時間と経過時間をjsonファイルに保存
        json_data = {
            'start_time': start_time.isoformat(),
            'elasped_seconds': self.elapsed_seconds,
        }

        with open(self.json_file_path, 'w') as f:
            json.dump(json_data, f, indent=4)


    # タイマーを開始して表示し、開始時間とCtrl+Spaceで停止した時間を返す
    def _get_start_and_end_time(self):
        # 開始時間を取得
        start_time = datetime.datetime.now()
        print('Started the timer. Press Ctrl+Space to stop it.')

        while True:
            # 経過時間を取得
            time_diff = datetime.datetime.now() - start_time
            time_diff_seconds = time_diff.total_seconds()
            # 残り時間を算出
            remain_seconds = self.limit_seconds - (self.elapsed_seconds + time_diff_seconds)
            # フォーマットを整える
            remain_time = self._format_seconds_to_hms(remain_seconds) if remain_seconds > 0 else 'Time limit exceeded!!'
            total_elapsed_time = self._format_seconds_to_hms(self.elapsed_seconds + time_diff_seconds)
            elapsed_time = self._format_seconds_to_hms(time_diff_seconds)

            if remain_seconds <= self.limit_seconds / 2 and self.half_msg_flag == False:
                self.half_msg_flag = True
                message_thread = threading.Thread(target=self._show_messagebox, args=(f'remain time is {remain_seconds//60} minutes',)) 
                message_thread.start()

            if remain_seconds <= 0 and self.end_msg_flag == False:
                self.end_msg_flag = True
                message_thread = threading.Thread(target=self._show_messagebox, args=('Time limit exceeded!!',)) 
                message_thread.start()

            # 表示
            print(f'\rremain:{remain_time} / total_elapsed:{total_elapsed_time} / elapsed:{elapsed_time}', end='')
            
            # Ctrl+Spaceが押されたら停止
            if keyboard.is_pressed('ctrl+space'):
                print('')
                break

            # 0.1だと長押ししないと反応しないので0.05にした
            time.sleep(0.05)
        
        # タイマー停止時間を取得
        end_time = datetime.datetime.now()

        return start_time, end_time

    def _show_messagebox(self, message):
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', 1) # 最前面に表示
        mbox.showwarning('GameTimer', message)
        root.destroy()

    # 秒数を時分秒形式に変換
    def _format_seconds_to_hms(self, seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        seconds, milliseconds = divmod(seconds, 1)

        return f'{int(hours):02}:{int(minutes):02}:{int(seconds):02}.{int(milliseconds*10):01}'


if __name__ == '__main__':
    main()