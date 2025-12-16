import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

import gspread  # https://docs.gspread.org/en/v5.12.1/
import pygetwindow as gw

from config_loader import (
    DEFAULT_BROWSERS,
    DEFAULT_EXCLUDED_TITLES,
    ConfigLoader,
)
from log_handler import LogHandler

POLL_INTERVAL_SECONDS = 10
MIN_PLAY_MINUTES = 5


@dataclass
class GameEntry:
    game_title: str
    window_title: str
    play_with_friends: bool
    is_browser_game: bool
    is_playing: bool = False
    start_time: Optional[datetime] = None


def main() -> None:
    config = ConfigLoader()
    monitor = GameMonitor(
        log_handler=LogHandler(),
        games=load_games_info(config),
        browsers=config.window_scan.get('browsers', DEFAULT_BROWSERS),
        excluded_titles=config.window_scan.get('excluded_titles', DEFAULT_EXCLUDED_TITLES),
        poll_interval=POLL_INTERVAL_SECONDS,
        min_play_minutes=MIN_PLAY_MINUTES,
    )
    monitor.run()


def is_game_detected(game: GameEntry, window_titles: Sequence[str], browsers: Sequence[str] = DEFAULT_BROWSERS) -> bool:
    for title in window_titles:
        if game.window_title not in title:
            continue

        is_browser = any(browser in title for browser in browsers)
        if game.is_browser_game:
            return True
        if not is_browser:
            return True
    return False


def finalize_game_session(
    game: GameEntry,
    log_handler: LogHandler,
    *,
    min_play_minutes: int = MIN_PLAY_MINUTES,
) -> None:
    end_time = datetime.now()
    start_time = game.start_time
    game.is_playing = False
    game.start_time = None

    if start_time is None:
        return

    play_duration = (end_time - start_time).total_seconds() / 60
    if play_duration < min_play_minutes:
        print(f'{game.game_title}のプレイ時間が{min_play_minutes}分未満のため、記録されませんでした')
        return

    start = log_handler.format_datetime_to_gss_style(start_time)
    end = log_handler.format_datetime_to_gss_style(end_time)
    log_handler.save_record([
        log_handler.get_and_increment_index(),
        start,
        end,
        game.game_title,
        game.play_with_friends,
    ])
    print(f'{game.game_title}のプレイ時間を記録しました')


def print_playing_games(games: Sequence[GameEntry]) -> None:
    for game in games:
        print(f'{game.game_title}をプレイ中')


def print_window_titles(window_titles: Sequence[str]) -> None:
    for title in window_titles:
        print(f'- {title}')


def clear_console() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')


def load_games_info(config: Optional[ConfigLoader] = None) -> List[GameEntry]:
    if config is None:
        config = ConfigLoader()
    gc = gspread.service_account(filename=Path(config.log_handler['cert_file_path']))
    sheet = gc.open_by_key(config.game_info['sheet_key']).get_worksheet_by_id(config.game_info['sheet_gid'])
    records = sheet.get_all_records()

    games: List[GameEntry] = []
    for record in records:
        games.append(GameEntry(
            game_title=str(record['game_title']),
            window_title=str(record['window_title']),
            play_with_friends=parse_bool(record['play_with_friends']),
            is_browser_game=parse_bool(record.get('is_browser_game', 'FALSE')),
        ))
    return games


def get_window_titles(excluded_titles: Sequence[str]) -> List[str]:
    titles = {window.title for window in gw.getAllWindows() if window.title}
    return [title for title in titles if title not in excluded_titles]


def parse_bool(value: object) -> bool:
    return str(value).upper() == 'TRUE'


class GameMonitor:
    def __init__(
        self,
        *,
        log_handler: LogHandler,
        games: List[GameEntry],
        browsers: Sequence[str],
        excluded_titles: Sequence[str],
        poll_interval: int = POLL_INTERVAL_SECONDS,
        min_play_minutes: int = MIN_PLAY_MINUTES,
    ) -> None:
        self.log_handler = log_handler
        self.games = games
        self.browsers = browsers
        self.excluded_titles = excluded_titles
        self.poll_interval = poll_interval
        self.min_play_minutes = min_play_minutes

    def run(self) -> None:
        while True:
            clear_console()
            window_titles = get_window_titles(self.excluded_titles)
            active_games = self._process_games(window_titles)

            if active_games:
                print_playing_games(active_games)
            else:
                print('ゲームをプレイしていません')
                print('現在のウィンドウタイトルは以下です。')
                print_window_titles(window_titles)

            time.sleep(self.poll_interval)

    def _process_games(self, window_titles: Sequence[str]) -> List[GameEntry]:
        active_games: List[GameEntry] = []
        for game in self.games:
            detected = is_game_detected(game, window_titles, self.browsers)
            if detected and not game.is_playing:
                game.is_playing = True
                game.start_time = datetime.now()
            elif not detected and game.is_playing:
                finalize_game_session(
                    game,
                    self.log_handler,
                    min_play_minutes=self.min_play_minutes,
                )

            if game.is_playing:
                active_games.append(game)
        return active_games


if __name__ == '__main__':
    main()
