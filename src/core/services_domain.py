"""ドメインロジック層 - ゲーム状態遷移と日次統計。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.core.models import GameEntry
from src.core.text_utils import normalize_title
from src.core.time_utils import SECONDS_PER_MINUTE

# 定数
MIN_PLAY_MINUTES = 5


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
