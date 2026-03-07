"""ビジネスロジック - ゲーム情報ローダー、ウィンドウスキャナー、セッション記録、統計追跡."""

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pygetwindow as gw

from config_loader import Config
from gspread_service import GspreadService
from log_handler import LogHandler
from models import GameEntry, ParsedRecord, parse_bool, parse_record
from text_utils import normalize_title
from time_utils import split_by_day

logger = logging.getLogger(__name__)

# 定数
MIN_PLAY_MINUTES = 5
SECONDS_PER_MINUTE = 60


@dataclass
class ScanResult:
    """ゲームスキャン結果を保持するデータクラス."""
    
    active_games: List[GameEntry]
    inactive_games: List[GameEntry]
    recorded_seconds: float  # この周期で記録された秒数


@dataclass(frozen=True)
class WindowMatchState:
    """Window match result for one game in one scan tick."""

    exists: bool
    is_foreground: bool


LoadTodayMinutes = Callable[[], Dict[str, float]]


class GameStateTracker:
    """ゲーム状態の追跡と遷移を管理するクラス.
    
    UIから独立した状態遷移ロジックを提供。
    scan()を呼び出すことで、ウィンドウ状態に基づいてゲーム状態を更新し、
    アクティブ/非アクティブなゲームと記録された秒数を返す。
    """
    
    def __init__(
        self,
        recorder: 'SessionRecorder',
        daily_stats: 'DailyStatsTracker',
        browsers: List[str],
        inactive_timeout_minutes: int,
    ) -> None:
        """初期化.
        
        Args:
            recorder: セッション記録用
            daily_stats: 日次統計追跡用
            browsers: ブラウザ名リスト
            inactive_timeout_minutes: 非アクティブタイムアウト時間（分）
        """
        self.recorder = recorder
        self.daily_stats = daily_stats
        self._browsers: List[str] = []
        self._normalized_browsers: List[str] = []
        self.set_browsers(browsers)
        self.inactive_timeout_minutes = inactive_timeout_minutes

    @property
    def browsers(self) -> List[str]:
        """Return a copy of configured browser names."""
        return list(self._browsers)

    def set_browsers(self, browsers: Sequence[str]) -> None:
        """Update browsers and keep normalized cache in sync."""
        self._browsers = list(browsers)
        self._normalized_browsers = [
            normalized
            for normalized in (normalize_title(browser) for browser in self._browsers)
            if normalized
        ]
    
    def scan(
        self,
        games: List[GameEntry],
        window_titles: List[str],
        foreground_title: Optional[str],
        load_today_game_minutes_callback: LoadTodayMinutes,
    ) -> ScanResult:
        """ゲーム状態をスキャンして更新.
        
        Args:
            games: 追跡するゲームのリスト
            window_titles: 現在のウィンドウタイトルリスト
            foreground_title: フォアグラウンドのウィンドウタイトル
            load_today_game_minutes_callback: 今日のゲーム時間を取得するコールバック
        
        Returns:
            ScanResult: アクティブ/非アクティブなゲームと記録秒数
        """
        active_games: List[GameEntry] = []
        inactive_games: List[GameEntry] = []
        total_recorded_seconds = 0.0
        
        normalized_window_titles, normalized_foreground_title = self._normalize_scan_inputs(
            window_titles, foreground_title
        )

        for game in games:
            match_state = self._resolve_window_match_state(
                game,
                normalized_window_titles,
                normalized_foreground_title,
            )
            
            if not game.is_playing:
                self._handle_not_playing(game, match_state.is_foreground, active_games)
            else:
                recorded_seconds = self._handle_playing(
                    game,
                    match_state,
                    active_games, inactive_games,
                    load_today_game_minutes_callback
                )
                total_recorded_seconds += recorded_seconds
        
        return ScanResult(
            active_games=active_games,
            inactive_games=inactive_games,
            recorded_seconds=total_recorded_seconds
        )

    def _normalize_scan_inputs(
        self,
        window_titles: Sequence[str],
        foreground_title: Optional[str],
    ) -> Tuple[List[str], Optional[str]]:
        """Normalize scan inputs once per tick."""
        normalized_window_titles = [normalize_title(title) for title in window_titles]
        normalized_foreground_title = (
            normalize_title(foreground_title) if foreground_title else None
        )
        return normalized_window_titles, normalized_foreground_title
    
    def _check_window_exists(
        self,
        game: GameEntry,
        window_titles: Sequence[str],
    ) -> bool:
        """Return True if any normalized window title matches this game."""
        return any(
            game.matches_window(title, self._normalized_browsers)
            for title in window_titles
        )

    def _check_is_foreground(
        self,
        game: GameEntry,
        foreground_title: Optional[str],
    ) -> bool:
        """Return True if the normalized foreground title matches this game."""
        return (
            foreground_title is not None
            and game.matches_window(foreground_title, self._normalized_browsers)
        )

    def _resolve_window_match_state(
        self,
        game: GameEntry,
        window_titles: Sequence[str],
        foreground_title: Optional[str],
    ) -> WindowMatchState:
        """Resolve window existence and foreground match state for a game."""
        return WindowMatchState(
            exists=self._check_window_exists(game, window_titles),
            is_foreground=self._check_is_foreground(game, foreground_title),
        )

    def _handle_not_playing(
        self,
        game: GameEntry,
        is_foreground: bool,
        active_games: List[GameEntry],
    ) -> None:
        """プレイ中でないゲームの状態遷移を処理."""
        if is_foreground:
            game.start_session()
            active_games.append(game)
    
    def _handle_playing(
        self,
        game: GameEntry,
        match_state: WindowMatchState,
        active_games: List[GameEntry],
        inactive_games: List[GameEntry],
        load_today_game_minutes_callback: LoadTodayMinutes,
    ) -> float:
        """プレイ中ゲームの状態遷移を処理.
        
        Returns:
            この処理で記録された秒数
        """
        # まず、非アクティブタイムアウトをチェック
        if game.is_inactive():
            inactive_seconds = game.get_inactive_seconds()
            if inactive_seconds >= self.inactive_timeout_minutes * SECONDS_PER_MINUTE:
                # タイムアウト：記録して状態をリセット
                recorded_seconds = self._handle_inactive_timeout(game, load_today_game_minutes_callback)
                # タイムアウト後、フォアグラウンドに戻っている場合は新しいセッションを開始
                if match_state.is_foreground and match_state.exists:
                    game.start_session()
                    active_games.append(game)
                return recorded_seconds
        
        # ウィンドウが消失した場合
        if not match_state.exists:
            return self._handle_window_closed(game, load_today_game_minutes_callback)
        # フォアグラウンドの場合
        elif match_state.is_foreground:
            self._handle_foreground(game, active_games)
            return 0.0
        # バックグラウンドの場合
        else:
            return self._handle_background(game, inactive_games)
    
    def _handle_window_closed(
        self,
        game: GameEntry,
        load_today_game_minutes_callback: LoadTodayMinutes,
    ) -> float:
        """ウィンドウが閉じられた場合の処理.
        
        Returns:
            記録された秒数
        """
        return self._apply_recorded_seconds(
            self.recorder.record(game),
            load_today_game_minutes_callback,
        )
    
    def _handle_foreground(self, game: GameEntry, active_games: List[GameEntry]) -> None:
        """フォアグラウンドになった場合の処理."""
        game.set_active()
        active_games.append(game)
    
    def _handle_background(
        self,
        game: GameEntry,
        inactive_games: List[GameEntry],
    ) -> float:
        """バックグラウンドに移行した場合の処理.
        
        Returns:
            この処理で記録された秒数
        """
        if not game.is_inactive():
            game.set_inactive()
        
        # 非アクティブリストに追加（タイムアウトチェックは_handle_playingで行われる）
        inactive_games.append(game)
        return 0.0
    
    def _handle_inactive_timeout(
        self,
        game: GameEntry,
        load_today_game_minutes_callback: LoadTodayMinutes,
    ) -> float:
        """非アクティブタイムアウト時の処理.
        
        Returns:
            記録された秒数
        """
        recorded_seconds = 0.0
        if game.start_time and game.inactive_since:
            recorded_seconds = self.recorder.record_with_times(
                game, game.start_time, game.inactive_since
            )
            recorded_seconds = self._apply_recorded_seconds(
                recorded_seconds,
                load_today_game_minutes_callback,
            )
        game.is_playing = False
        game.start_time = None
        game.inactive_since = None
        return recorded_seconds

    def _apply_recorded_seconds(
        self,
        recorded_seconds: Optional[float],
        load_today_game_minutes_callback: LoadTodayMinutes,
    ) -> float:
        """Apply recorded seconds to daily stats and normalize the return value."""
        if not recorded_seconds:
            return 0.0

        self.daily_stats.add_completed_seconds(recorded_seconds)
        self.daily_stats.update_game_minutes_cache(load_today_game_minutes_callback())
        return recorded_seconds


class Messages:
    """ユーザー向けメッセージ定義."""

    GAME_RECORDED = '{game_title}のプレイ時間を記録しました'
    GAME_TOO_SHORT = '{game_title}のプレイ時間が{min_minutes}分未満のため、記録されませんでした'
    NO_GAME_PLAYING = 'ゲームをプレイしていません'


class GameInfoLoader:
    """スプレッドシートからゲーム情報を読み込むクラス."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def load(self) -> List[GameEntry]:
        """ゲーム情報をスプレッドシートから読み込む."""
        try:
            gspread_service = GspreadService(
                cert_file_path=self.config.log_handler.cert_file_path,
                sheet_key=self.config.game_info.sheet_key,
                sheet_gid=self.config.game_info.sheet_gid,
            )
            records = gspread_service.get_all_records()
        except FileNotFoundError as e:
            logger.error(f'認証情報ファイルが見つかりません: {e}')
            return []
        except Exception as e:
            logger.error(f'ゲーム情報の読み込みに失敗しました: {e}')
            return []

        return [self._record_to_entry(record) for record in records]

    @staticmethod
    def _record_to_entry(record: dict) -> GameEntry:
        """スプレッドシートのレコードを GameEntry に変換."""
        return GameEntry(
            game_title=str(record['game_title']),
            window_title=str(record['window_title']),
            play_with_friends=parse_bool(record.get('play_with_friends', 'FALSE')),
            is_browser_game=parse_bool(record.get('is_browser_game', 'FALSE')),
        )


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

    def get_foreground_title(self) -> Optional[str]:
        """フォアグラウンド（最前面）ウィンドウのタイトルを取得.
        
        Returns:
            フォアグラウンドウィンドウのタイトル。取得できない場合はNone。
        """
        try:
            active_window = gw.getActiveWindow()
            if active_window and active_window.title:
                return active_window.title
        except Exception:
            # pygetwindowの内部エラーは無視（ウィンドウが存在しない場合など）
            pass
        return None


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
        """ゲームセッションを終了して記録。日を跨いだ場合は分割。

        Returns:
            当日分のみの記録秒数。書き込み失敗時はNone。
        """
        start_time, end_time = game.end_session()

        if start_time is None or end_time is None:
            return None

        return self._record_segments(game, start_time, end_time)

    def record_with_times(
        self,
        game: GameEntry,
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[float]:
        """指定された開始・終了時刻でセッションを記録。日を跨いだ場合は分割。
        
        ゲームの状態（is_playing, start_time）は変更しない。
        
        Returns:
            当日分のみの記録秒数。5分未満や書き込み失敗など保存が一件も発生しない場合はNone。
        """
        return self._record_segments(game, start_time, end_time)

    def _record_segments(
        self,
        game: GameEntry,
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[float]:
        """セグメント分割と記録の共通ロジック.
        
        Returns:
            当日分のみの記録秒数。保存が一件も発生しない場合はNone。
        """
        today = datetime.now().date()
        today_seconds = 0.0
        any_saved = False
        segments = split_by_day(start_time, end_time)

        for seg_start, seg_end in segments:
            play_minutes = (seg_end - seg_start).total_seconds() / SECONDS_PER_MINUTE
            if play_minutes >= self.min_play_minutes:
                success = self._save_to_spreadsheet(game, seg_start, seg_end)
                if success:
                    any_saved = True
                    # 当日分のみ加算
                    if seg_start.date() == today:
                        today_seconds += (seg_end - seg_start).total_seconds()
                    logger.info(Messages.GAME_RECORDED.format(game_title=game.game_title))
                else:
                    logger.warning(f'{game.game_title}の記録保存に失敗しました')
            else:
                logger.debug(Messages.GAME_TOO_SHORT.format(
                    game_title=game.game_title,
                    min_minutes=self.min_play_minutes,
                ))

        return today_seconds if any_saved else None

    def _save_to_spreadsheet(
        self,
        game: GameEntry,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """スプレッドシートに記録を保存.

        Returns:
            保存成功時True、失敗時False。
        """
        return self.log_handler.save_record([
            self.log_handler.get_and_increment_index(),
            self.log_handler.format_datetime_to_gss_style(start_time),
            self.log_handler.format_datetime_to_gss_style(end_time),
            game.game_title,
            game.play_with_friends,
        ])


class DailyStatsTracker:
    """日付ごとの統計を追跡し、日付変更時にリセットするクラス."""

    def __init__(self, get_current_date: Optional[Callable[[], Any]] = None) -> None:
        """初期化。get_current_dateはテスト用に日付取得関数を差し替え可能."""
        self._get_current_date = get_current_date or (lambda: datetime.now().date())
        self._last_checked_date = self._get_current_date()
        self.today_completed_seconds: float = 0.0
        self.today_game_minutes_cache: Dict[str, float] = {}
        self.last_today_games_content: str = ""

    def check_day_change(self) -> bool:
        """日付が変わったかチェックし、変わっていればリセット。変更があればTrueを返す."""
        today = self._get_current_date()
        if today != self._last_checked_date:
            self._last_checked_date = today
            self.today_completed_seconds = 0.0
            self.today_game_minutes_cache = {}
            self.last_today_games_content = ""
            return True
        return False

    def add_completed_seconds(self, seconds: float) -> None:
        """完了したプレイ時間を追加."""
        self.today_completed_seconds += seconds

    def update_game_minutes_cache(self, cache: Dict[str, float]) -> None:
        """ゲームごとのプレイ時間キャッシュを更新."""
        self.today_game_minutes_cache = cache
