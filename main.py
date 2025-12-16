"""Game Time Tracker - ウィンドウタイトルからゲームプレイを自動検出し記録するツール."""

import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

import gspread
import pygetwindow as gw

from config_loader import (
    DEFAULT_BROWSERS,
    DEFAULT_EXCLUDED_TITLES,
    ConfigLoader,
)
from log_handler import LogHandler


# =============================================================================
# 定数
# =============================================================================
POLL_INTERVAL_SECONDS = 1
MIN_PLAY_MINUTES = 5


class Messages:
    """ユーザー向けメッセージ定義."""

    GAME_PLAYING = '{game_title}をプレイ中'
    GAME_PLAYING_WITH_ELAPSED = '{game_title}をプレイ中（経過: {elapsed}）'
    GAME_RECORDED = '{game_title}のプレイ時間を記録しました'
    GAME_TOO_SHORT = '{game_title}のプレイ時間が{min_minutes}分未満のため、記録されませんでした'
    NO_GAME_PLAYING = 'ゲームをプレイしていません'
    CURRENT_WINDOWS = '現在のウィンドウタイトルは以下です。'


# =============================================================================
# データクラス
# =============================================================================
@dataclass
class GameEntry:
    """ゲーム情報を保持するデータクラス."""

    game_title: str
    window_title: str
    play_with_friends: bool = False
    is_browser_game: bool = False
    is_playing: bool = field(default=False, compare=False)
    start_time: Optional[datetime] = field(default=None, compare=False)

    def matches_window(self, window_title: str, browsers: Sequence[str]) -> bool:
        """ウィンドウタイトルがこのゲームに該当するか判定."""
        if self.window_title not in window_title:
            return False

        is_browser = any(browser in window_title for browser in browsers)

        # ブラウザゲームの場合は常にマッチ
        if self.is_browser_game:
            return True

        # 通常ゲームの場合はブラウザ以外でマッチ
        return not is_browser

    def start_session(self) -> None:
        """ゲームセッションを開始."""
        self.is_playing = True
        self.start_time = datetime.now()

    def end_session(self) -> tuple[Optional[datetime], Optional[datetime]]:
        """ゲームセッションを終了し、開始・終了時刻を返す."""
        start_time = self.start_time
        end_time = datetime.now() if start_time else None
        self.is_playing = False
        self.start_time = None
        return start_time, end_time


# =============================================================================
# ゲーム情報ローダー
# =============================================================================
class GameInfoLoader:
    """スプレッドシートからゲーム情報を読み込むクラス."""

    def __init__(self, config: ConfigLoader) -> None:
        self.config = config

    def load(self) -> List[GameEntry]:
        """ゲーム情報をスプレッドシートから読み込む."""
        try:
            gc = gspread.service_account(
                filename=Path(self.config.log_handler['cert_file_path'])
            )
            sheet = gc.open_by_key(
                self.config.game_info['sheet_key']
            ).get_worksheet_by_id(
                self.config.game_info['sheet_gid']
            )
            records = sheet.get_all_records()
        except gspread.exceptions.APIError as e:
            print(f'スプレッドシートの読み込みに失敗しました: {e}')
            return []

        return [self._record_to_entry(record) for record in records]

    @staticmethod
    def _record_to_entry(record: dict) -> GameEntry:
        """スプレッドシートのレコードを GameEntry に変換."""
        return GameEntry(
            game_title=str(record['game_title']),
            window_title=str(record['window_title']),
            play_with_friends=_parse_bool(record.get('play_with_friends', 'FALSE')),
            is_browser_game=_parse_bool(record.get('is_browser_game', 'FALSE')),
        )


# =============================================================================
# ウィンドウスキャナー
# =============================================================================
class WindowScanner:
    """アクティブなウィンドウタイトルを取得するクラス."""

    def __init__(self, excluded_titles: Sequence[str]) -> None:
        self.excluded_titles = set(excluded_titles)

    def get_titles(self) -> List[str]:
        """除外リストを考慮してウィンドウタイトルを取得."""
        titles = {
            window.title
            for window in gw.getAllWindows()
            if window.title and window.title not in self.excluded_titles
        }
        return list(titles)


# =============================================================================
# ゲームセッション記録
# =============================================================================
class SessionRecorder:
    """ゲームセッションをスプレッドシートに記録するクラス."""

    def __init__(
        self,
        log_handler: LogHandler,
        min_play_minutes: int = MIN_PLAY_MINUTES,
    ) -> None:
        self.log_handler = log_handler
        self.min_play_minutes = min_play_minutes

    def record(self, game: GameEntry) -> Optional[float]:
        """ゲームセッションを終了して記録し、保存した秒数を返す."""
        start_time, end_time = game.end_session()

        if start_time is None or end_time is None:
            return None

        play_minutes = (end_time - start_time).total_seconds() / 60

        if play_minutes < self.min_play_minutes:
            print(Messages.GAME_TOO_SHORT.format(
                game_title=game.game_title,
                min_minutes=self.min_play_minutes,
            ))
            return None

        duration_seconds = (end_time - start_time).total_seconds()
        self._save_to_spreadsheet(game, start_time, end_time)
        print(Messages.GAME_RECORDED.format(game_title=game.game_title))
        return duration_seconds

    def _save_to_spreadsheet(
        self,
        game: GameEntry,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """スプレッドシートに記録を保存."""
        self.log_handler.save_record([
            self.log_handler.get_and_increment_index(),
            self.log_handler.format_datetime_to_gss_style(start_time),
            self.log_handler.format_datetime_to_gss_style(end_time),
            game.game_title,
            game.play_with_friends,
        ])


# =============================================================================
# ゲームモニター
# =============================================================================
class GameMonitor:
    """ゲームプレイを監視するメインクラス."""

    def __init__(
        self,
        *,
        games: List[GameEntry],
        scanner: WindowScanner,
        recorder: SessionRecorder,
        browsers: Sequence[str] = DEFAULT_BROWSERS,
        poll_interval: int = POLL_INTERVAL_SECONDS,
    ) -> None:
        self.games = games
        self.scanner = scanner
        self.recorder = recorder
        self.browsers = browsers
        self.poll_interval = poll_interval

    def run(self) -> None:
        """監視ループを開始."""
        print('Game Time Tracker を開始しました。Ctrl+C で終了します。')
        try:
            while True:
                self._tick()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            print('\n終了します。')
            self._finalize_all_sessions()

    def _tick(self) -> None:
        """1回の監視サイクルを実行."""
        _clear_console()
        window_titles = self.scanner.get_titles()
        active_games = self._update_game_states(window_titles)
        self._display_status(active_games, window_titles)

    def _update_game_states(self, window_titles: List[str]) -> List[GameEntry]:
        """全ゲームの状態を更新し、アクティブなゲームを返す."""
        active_games: List[GameEntry] = []

        for game in self.games:
            detected = any(
                game.matches_window(title, self.browsers)
                for title in window_titles
            )

            if detected and not game.is_playing:
                game.start_session()
            elif not detected and game.is_playing:
                self.recorder.record(game)

            if game.is_playing:
                active_games.append(game)

        return active_games

    def _display_status(
        self,
        active_games: List[GameEntry],
        window_titles: List[str],
    ) -> None:
        """現在の状態を表示."""
        if active_games:
            for game in active_games:
                elapsed = _format_elapsed(game.start_time)
                print(Messages.GAME_PLAYING_WITH_ELAPSED.format(
                    game_title=game.game_title,
                    elapsed=elapsed,
                ))
        else:
            print(Messages.NO_GAME_PLAYING)
            print(Messages.CURRENT_WINDOWS)
            for title in window_titles:
                print(f'- {title}')

    def _finalize_all_sessions(self) -> None:
        """全てのアクティブセッションを終了."""
        for game in self.games:
            if game.is_playing:
                self.recorder.record(game)


# =============================================================================
# ユーティリティ関数
# =============================================================================
def _parse_bool(value: object) -> bool:
    """文字列を bool に変換."""
    return str(value).upper() == 'TRUE'


def _format_elapsed(start_time: Optional[datetime]) -> str:
    """開始時刻からの経過時間を整形."""
    if start_time is None:
        return '0秒'
    delta_seconds = int((datetime.now() - start_time).total_seconds())
    minutes, seconds = divmod(delta_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours}時間{minutes}分{seconds}秒'
    if minutes:
        return f'{minutes}分{seconds}秒'
    return f'{seconds}秒'


def _clear_console() -> None:
    """コンソールをクリア."""
    os.system('cls' if os.name == 'nt' else 'clear')


# =============================================================================
# エントリーポイント
# =============================================================================
def main() -> None:
    """アプリケーションのエントリーポイント."""
    config = ConfigLoader()

    # コンポーネントの初期化
    games = GameInfoLoader(config).load()
    if not games:
        print('ゲーム情報が取得できませんでした。config.ini を確認してください。')
        return

    scanner = WindowScanner(
        excluded_titles=config.window_scan.get('excluded_titles', DEFAULT_EXCLUDED_TITLES)
    )
    recorder = SessionRecorder(
        log_handler=LogHandler(),
        min_play_minutes=MIN_PLAY_MINUTES,
    )

    # モニター開始
    monitor = GameMonitor(
        games=games,
        scanner=scanner,
        recorder=recorder,
        browsers=config.window_scan.get('browsers', DEFAULT_BROWSERS),
        poll_interval=POLL_INTERVAL_SECONDS,
    )
    monitor.run()


if __name__ == '__main__':
    main()
