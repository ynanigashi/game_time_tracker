import os
import time

import keyboard

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
        playing_title = None
        if use_spreadsheet:
            playing_title = select_game_title()
            print(f'プレイするゲームは{playing_title}です')
        print(f'本日の残り時間は{(gt.limit_seconds - gt.elapsed_seconds)//60}分です')
        play_with_friends = True if input('友人とプレイする場合はyを入力してください: ') in ['y', 'Y', 'ｙ', 'Ｙ'] else False
        if play_with_friends:
            print('友人とプレイします, 本日の残り時間は減少しません')
        else:
            print('一人でプレイします, 本日の残り時間が減少します')

        input('Enterを押すとタイマーが開始します:')
        clear_console()
        if use_spreadsheet:
            print(f'プレイ中のゲームは{playing_title}です')
        start_time, end_time = gt.timer(play_with_friends=play_with_friends)
        # print(f'開始時間:{start_time} / 終了時間:{end_time}')

        # google spreadsheetのフォーマットに変換
        formatted_start_time = format_datetime_to_gss_style(start_time)
        formatted_end_time = format_datetime_to_gss_style(end_time)

        if use_spreadsheet:
            # スプレッドシートに保存
            log_handler.save_record([log_handler.get_and_incremant_index(), 
                                     formatted_start_time, 
                                     formatted_end_time, 
                                     playing_title, 
                                     play_with_friends])
            print('スプレッドシートにプレイ時間を保存しました')
        else:
            print('プレイ時間は以下の通りです')
            print(f'start time:\n{formatted_start_time}')
            print(f'end time:\n{formatted_end_time}')


def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')


def format_datetime_to_gss_style(datetime):
    return datetime.strftime("%Y/%m/%d %H:%M:%S")

def select_game_title():
    log_handler = LogHandler()
    titles = [
        record['title'] for record in
        log_handler.get_5_titles_of_recently()
        ] 
    titles.append('新しいゲームを追加する')
    selected = 0
    while True:
        clear_console()
        print('プレイするゲームを上下で選択してください')
        for i, title in enumerate(titles):
            if i == selected:
                print(f'\033[1;30;47m-> {title} \033[0m')
            else:
                print(f'   {title}')
        print('Enterで決定')
        key = keyboard.read_key()
        if key == 'up':
            selected = selected - 1 if selected > 0 else len(titles) - 1
            time.sleep(0.1)
        if key == 'down':
            selected = selected + 1 if selected < len(titles) - 1 else 0
            time.sleep(0.1)
        if key == 'enter':
            # keaboard.read_key()でEnterが読み込まれてしまうのでここで使っておく
            _ = input()
            break

        time.sleep(0.05)
    
    if selected == len(titles) - 1:
        while True:
            clear_console()
            print('プレイするゲームの名前を入力してください')
            title = input('ゲーム名: ')

            print(f'上記の名前でよろしいですか？')
            if input('y/n: ') in ['y', 'Y', 'ｙ', 'Ｙ']:
                break
        
        return title

    return titles[selected]

if __name__ == '__main__':
    main()