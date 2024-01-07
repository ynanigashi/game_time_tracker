import time
import datetime
import json
import configparser

import keyboard

# 設定ファイルの読み込み
def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')

    return config

def main():
    # 設定ファイルの読み込み
    config = load_config()
    
    # プレイ可能時間の読み込み
    limit_seconds = int(config['DEFAULT']['limit_minutes']) * 60
    
    # 前回以前の経過時間を取得
    json_file_path = config['DEFAULT']['json_file_path']
    elapsed_seconds = get_elapsed_seconds_from(json_file_path)
    
    # プレイ時間の計測
    start_time, end_time = get_start_and_end_time(limit_seconds, elapsed_seconds)
    
    # 経過時間を加算
    elapsed_seconds += (end_time - start_time).total_seconds()
    
    # 開始時間と経過時間をjsonファイルに保存
    json_data = {
        'start_time': start_time.isoformat(),
        'elasped_seconds': elapsed_seconds,
    }

    with open(json_file_path, 'w') as f:
        json.dump(json_data, f, indent=4)
     
    # google spreadsheetのフォーマットに変換して表示
    formatted_start_time = format_datetime_to_gss_style(start_time)
    formatted_end_time = format_datetime_to_gss_style(end_time)
    print(f'start time:\n{formatted_start_time}')
    print(f'end time:\n{formatted_end_time}')


# get elapsed minutes from json file
def get_elapsed_seconds_from(json_file_path):
    try:
        with open(json_file_path, 'r') as f:
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


# タイマーを開始して表示し、開始時間とCtrl+Spaceで停止した時間を返す
def get_start_and_end_time(limit_seconds, elapsed_seconds):
    # 開始時間を取得
    start_time = datetime.datetime.now()
    print('Started the timer. Press Ctrl+Space to stop it.')
    while True:
        # 経過時間を取得
        time_diff = datetime.datetime.now() - start_time
        time_diff_seconds = time_diff.total_seconds()
        # 残り時間を算出
        remain_seconds = limit_seconds - (elapsed_seconds + time_diff_seconds)
        # フォーマットを整える
        remain_time = format_seconds_to_hms(remain_seconds) if remain_seconds > 0 else 'Time limit exceeded!!'
        total_elapsed_time = format_seconds_to_hms(elapsed_seconds + time_diff_seconds)
        elapsed_time = format_seconds_to_hms(time_diff_seconds)

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


# 秒数を時分秒形式に変換
def format_seconds_to_hms(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    seconds, milliseconds = divmod(seconds, 1)

    return f'{int(hours):02}:{int(minutes):02}:{int(seconds):02}.{int(milliseconds*10):01}'
    
# datetimeをgoogle spreadsheetのフォーマットに変換
def format_datetime_to_gss_style(datetime):
    return datetime.strftime("%Y/%m/%d %H:%M:%S")


if __name__ == '__main__':
    main()