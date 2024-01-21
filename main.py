import os
import time
import json

import keyboard

from game_timer import GameTimer
from config_loader import ConfigLoader
from log_handler import LogHandler

def main():
    gt = GameTimer()
    config = ConfigLoader()
    prompts = get_prompts()

    # スプレッドシートを使用するか取得
    use_spreadsheet = config.application_manager['use_spreadsheet']

    if use_spreadsheet:
        # スプレッドシートの設定
        log_handler = LogHandler()
    
    while True:
        playing_title = None
        if use_spreadsheet:
            playing_title = select_game_title(prompts['select_game_title'])
            print(prompts['selected_title'].format(
                        playing_title=playing_title))
        remain_minutes = (gt.limit_seconds - gt.elapsed_seconds)//60
        print(prompts['remain_minutes'].format(
                    remain_minutes=remain_minutes))
        play_with_friends = True if input(prompts['with_friends_input']) in ['y', 'Y', 'ｙ', 'Ｙ'] else False
        if play_with_friends:
            print(prompts['with_friends'])
        else:
            print(prompts['without_friends'])

        input(prompts['start_input'])
        clear_console()
        if use_spreadsheet:
            print(prompts['playing_title'].format(playing_title=playing_title))
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
            print(prompts['save_to_gss_done'])


def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')


def format_datetime_to_gss_style(datetime):
    return datetime.strftime("%Y/%m/%d %H:%M:%S")

def select_game_title(prompts):
    log_handler = LogHandler()
    titles = [
        record['title'] for record in
        log_handler.get_5_titles_of_recently()
        ] 
    titles.append(prompts['add_title_option'])
    selected = 0
    while True:
        clear_console()
        print(prompts['game_selection_guide'])
        for i, title in enumerate(titles):
            if i == selected:
                print(f'\033[1;30;47m-> {title} \033[0m')
            else:
                print(f'   {title}')
        print(prompts['game_choice_guide'])
        
        # キー入力を取得
        key = keyboard.read_key()
        
        # キー入力に応じて処理
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
    
    # ゲームを追加する場合
    if selected == len(titles) - 1:
        add_title_prompt = prompts['add_title']
        while True:
            clear_console()
            print(add_title_prompt['input_title'])
            title = input(add_title_prompt['title_input'])

            print(add_title_prompt['confirm_title'])
            if input(add_title_prompt['yn_input']) in ['y', 'Y', 'ｙ', 'Ｙ']:
                break
        
        return title

    return titles[selected]

def get_prompts():
    with open('jp_prompts.json', 'r', encoding='utf-8') as f:
        prompts = json.load(f)
    
    return prompts


if __name__ == '__main__':
    main()