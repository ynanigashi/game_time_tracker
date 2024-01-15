import os

from game_timer import GameTimer
from config_loader import ConfigLoader
from log_handler import LogHandler

def main():
    gt = GameTimer()
    config = ConfigLoader()
    # スプレッドシートを使用するか取得
    use_spreadsheet = config.application_manager['use_spreadsheet']

    if use_spreadsheet:
        # スプレッドシートの設定
        log_handler = LogHandler()
    
    while True:
        print(f'本日の残り時間は{(gt.limit_seconds - gt.elapsed_seconds)//60}分です')
        play_with_friends = True if input('友人とプレイする場合はyを入力してください: ') in ['y', 'Y', 'ｙ', 'Ｙ'] else False
        if play_with_friends:
            print('友人とプレイします, 本日の残り時間は減少しません')
        else:
            print('一人でプレイします, 本日の残り時間が減少します')

        input('Enterを押すとタイマーが開始します:')
        clear_console()
        start_time, end_time = gt.timer(play_with_friends=play_with_friends)
        # print(f'開始時間:{start_time} / 終了時間:{end_time}')

        # google spreadsheetのフォーマットに変換して表示
        formatted_start_time = format_datetime_to_gss_style(start_time)
        formatted_end_time = format_datetime_to_gss_style(end_time)

        if use_spreadsheet:
            # スプレッドシートに保存
            log_handler.save_record([formatted_start_time, formatted_end_time, '', play_with_friends])
            print('スプレッドシートにプレイ時間を保存しました')
        else:
            print('以下はgoogle spreadsheetのフォーマットに変換した時間')
            print(f'start time:\n{formatted_start_time}')
            print(f'end time:\n{formatted_end_time}')


def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')


def format_datetime_to_gss_style(datetime):
    return datetime.strftime("%Y/%m/%d %H:%M:%S")


if __name__ == '__main__':
    main()