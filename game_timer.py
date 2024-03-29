import time
import datetime
import json
import threading

import tkinter as tk
from tkinter import messagebox as mbox
import keyboard

from config_loader import ConfigLoader


# タイマー関連の処理
class GameTimer():
    
    def __init__(self):
        # 設定ファイルの読み込み
        config = ConfigLoader()
        
        ## 設定ファイルから各種設定を読み込む
        # 制限時間を取得
        self.limit_seconds = config.game_timer['limit_seconds']
        
        # jsonファイルのパスを取得
        self.json_file_path = config.game_timer['json_file_path']
        
        # jsonファイルから経過時間とフラグデータを取得
        (self.elapsed_seconds,
         self.half_msg_flag,
         self.end_msg_flag,
         ) = self._load_state()
    
    # get elapsed minutes from json file
    def _load_state(self):
        # set default values
        elapsed_seconds = 0
        half_msg_flag = False
        end_msg_flag = False
        
        try:
            with open(self.json_file_path, 'r') as f:
                json_data = json.load(f)
                start_time = datetime.datetime.fromisoformat(json_data['start_time'])

                # 日付が変わっていなければ経過時間やフラグデータを取得
                if start_time.date() == datetime.datetime.now().date():
                    elapsed_seconds = json_data['elasped_seconds']
                    half_msg_flag = json_data['half_msg_flag']
                    end_msg_flag = json_data['end_msg_flag']

        # ファイルがない場合はデフォルト値を返す
        except (FileNotFoundError, KeyError):
            pass
        
        return elapsed_seconds, half_msg_flag, end_msg_flag


    def timer(self, play_with_friends=False):
        # プレイ時間の計測
        start_time, end_time = self._get_start_and_end_time(play_with_friends=play_with_friends)

        # フレンドとプレイした場合は経過時間を加算・保存しない
        if not play_with_friends:        
            # 経過時間を加算
            self.elapsed_seconds += (end_time - start_time).total_seconds()

            # 経過時間を保存
            self._save_state(start_time)

        return start_time, end_time

    def _save_state(self, start_time):
        # 開始時間と経過時間をjsonファイルに保存
        json_data = {
            'start_time': start_time.isoformat(),
            'elasped_seconds': self.elapsed_seconds,
            'half_msg_flag': self.half_msg_flag,
            'end_msg_flag': self.end_msg_flag,
        }

        with open(self.json_file_path, 'w') as f:
            json.dump(json_data, f, indent=4)


    # タイマーを開始して表示し、開始時間とCtrl+Spaceで停止した時間を返す
    def _get_start_and_end_time(self, play_with_friends=False):
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
            remain_time = 'have fun!!' if play_with_friends \
                else self._format_seconds_to_hms(remain_seconds) \
                if remain_seconds > 0 else 'Time limit exceeded!!'
            total_elapsed_time = self._format_seconds_to_hms(self.elapsed_seconds + time_diff_seconds)
            elapsed_time = self._format_seconds_to_hms(time_diff_seconds)

            # 表示
            print(f'\rremain:{remain_time} / total_elapsed:{total_elapsed_time} / elapsed:{elapsed_time}', end='')
            
            # Ctrl+Spaceが押されたら停止
            if keyboard.is_pressed('ctrl+space'):
                print('')
                break

            # 0.1だと長押ししないと反応しないので0.05にした
            time.sleep(0.05)

            # 友人とプレイしている場合は残り時間でアラートを出さない
            if play_with_friends:
                continue

            # 残り時間が半分を切ったらメッセージを表示
            if remain_seconds <= self.limit_seconds / 2 and self.half_msg_flag == False:
                self.half_msg_flag = True
                message_thread = threading.Thread(target=self._show_messagebox, args=(f'remain time is {remain_seconds//60} minutes',)) 
                message_thread.start()

            # 残り時間が0を切ったらメッセージを表示
            if remain_seconds <= 0 and self.end_msg_flag == False:
                self.end_msg_flag = True
                message_thread = threading.Thread(target=self._show_messagebox, args=('Time limit exceeded!!',)) 
                message_thread.start()
        
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

def main():
    pass

if __name__ == '__main__':
    main()