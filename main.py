from datetime import datetime
import time
import os

from datetime import datetime

# https://docs.gspread.org/en/v5.12.1/
import gspread

from config_loader import ConfigLoader

import pygetwindow as gw

from log_handler import LogHandler

BROWSERS = ['Google Chrome', 
            'Microsoft Edge', 
            'Mozilla Firefox', 
            'Opera', 
            'Brave', 
            'Vivaldi', 
            'Safari', ]

def main():
    log_handler = LogHandler()
    games = get_games_info()
    while True:
        clear_console()
        window_titles = get_window_titles()
        is_any_game_playing = False
        for game in games:
            game_in_window_titles = False
            # terraria's window title is always changed
            # so I need to check if the game's title is included in the window title
            for title in window_titles:
                is_browser = False
                for browser in BROWSERS:
                    if browser in title:
                        is_browser = True
                        break
                
                # ゲームのウィンドウタイトルが含まれているかチェック
                if game['window_title'] in title:
                    # ブラウザゲームの場合：ブラウザでの実行を許可
                    # 通常のゲームの場合：ブラウザでの実行を拒否
                    if game['is_browser_game']:
                        # ブラウザゲームとして登録されている場合は、ブラウザでも記録
                        game_in_window_titles = True
                        break
                    elif not is_browser:
                        # 通常のゲームの場合は、ブラウザ以外でのみ記録
                        game_in_window_titles = True
                        break
            
            if game_in_window_titles:
                game['is_playing'] = True
                is_any_game_playing = True
                if game['start_time'] == '':
                    game['start_time'] = datetime.now()

            else:
                if game['is_playing']:
                    game['end_time'] = datetime.now()
                    play_duration = (game['end_time'] - game['start_time']).total_seconds() / 60
                    if play_duration >= 5:
                        start_time = log_handler.format_datetime_to_gss_style(game['start_time'])
                        end_time = log_handler.format_datetime_to_gss_style(game['end_time'])
                        log_handler.save_record([log_handler.get_and_incremant_index(), 
                                                 start_time, 
                                                 end_time, 
                                                 game['game_title'], 
                                                 game['play_with_friends']])
                        print(f'{game["game_title"]}のプレイ時間を記録しました')
                    else:
                        print(f'{game["game_title"]}のプレイ時間が5分未満のため、記録されませんでした')
                    # reset
                    game['start_time'] = ''
                    game['end_time'] = ''
                game['is_playing'] = False
        if is_any_game_playing:
            print_playing_games(games)
        else:
            print('ゲームをプレイしていません')
            print('現在のウィンドウタイトルは以下です。')
            print_window_titles(window_titles)

        time.sleep(10)


def print_playing_games(games):
    for game in games:
        if game['is_playing']:
            print(f'{game["game_title"]}をプレイ中')

def print_window_titles(window_titles):
    for title in window_titles:
        print(f'- {title}')


def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')


def get_games_info():
    config = ConfigLoader()
    gc = gspread.service_account(filename=config.log_handler['cert_file_path'])
    sheet = gc.open_by_key(config.game_info['sheet_key']).get_worksheet_by_id(config.game_info['sheet_gid'])
    records = sheet.get_all_records()

    games = []
    for record in records:
        game = {'game_title':record['game_title'],
                'window_title':record['window_title'],
                'is_playing':False,
                'start_time':'',
                'end_time':'',
                'play_with_friends':True if record['play_with_friends'] == 'TRUE' else False,
                'is_browser_game':True if record.get('is_browser_game', 'FALSE') == 'TRUE' else False,
                }
        games.append(game)

    return games


def get_window_titles():
    exclude_titles = [
        'Program Manager',
        'Settings',
        '設定',
        'NVIDIA GeForce Overlay',
        'Windows 入力エクスペリエンス',
        'Microsoft Store',
        'game_time_tracker.bat',
        'Nahimic',
    ]
    titles = set()
    all_windows = gw.getAllWindows()
    for window in all_windows:
        if window.title != '':
            titles.add(window.title)
    
    titles = [title for title in titles if title not in exclude_titles]

    return titles


if __name__ == '__main__':
    main()
    #print(get_window_titles())