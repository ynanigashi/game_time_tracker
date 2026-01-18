"""Game Time Tracker - PySide6 GUI."""

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import gspread
import pygetwindow as gw
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QApplication, QWidget, QTableWidgetItem

from config_loader import DEFAULT_BROWSERS, DEFAULT_EXCLUDED_TITLES, ConfigLoader
from gui_layout import LayoutWidgets, build_main_layout
from log_handler import LogHandler


# =============================================================================
# 定数
# =============================================================================
POLL_INTERVAL_SECONDS = 1
MIN_PLAY_MINUTES = 5
INACTIVE_TIMEOUT_MINUTES = 5  # 非アクティブ状態でこの時間経過でセッション分割
STATE_FILE = Path("window_state.txt")
BASE_TITLE = "Game Time Tracker"
UI_REFRESH_INTERVAL_SECONDS = 0.1
DISPLAY_MODES = ("max", "mid", "min")
MODE_DEFAULT_SIZES = {
    "max": (480, 400),
    "mid": (480, 300),
    "min": (320, 180),
}
MAX_WIDGET_HEIGHT = 16777215  # Qt default max height
TIME_FRACTION_PRECISION = 10  # 0.1秒単位での時間表示精度


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
    inactive_since: Optional[datetime] = field(default=None, compare=False)

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
        self.inactive_since = None

    def end_session(self) -> tuple[Optional[datetime], Optional[datetime]]:
        """ゲームセッションを終了し、開始・終了時刻を返す."""
        start_time = self.start_time
        end_time = datetime.now() if start_time else None
        self.is_playing = False
        self.start_time = None
        self.inactive_since = None
        return start_time, end_time

    def set_inactive(self) -> None:
        """非アクティブ状態に設定."""
        if self.inactive_since is None:
            self.inactive_since = datetime.now()

    def set_active(self) -> None:
        """アクティブ状態に戻す（非アクティブ時間をクリア）."""
        self.inactive_since = None

    def is_inactive(self) -> bool:
        """非アクティブ状態かどうか."""
        return self.inactive_since is not None

    def get_inactive_seconds(self) -> float:
        """非アクティブ経過秒数を取得."""
        if self.inactive_since is None:
            return 0.0
        return (datetime.now() - self.inactive_since).total_seconds()


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
            pass
        return None


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
        """ゲームセッションを終了して記録。日を跨いだ場合は分割。

        Returns:
            当日分のみの記録秒数。書き込み失敗時はNone。
        """
        start_time, end_time = game.end_session()

        if start_time is None or end_time is None:
            return None

        today = datetime.now().date()
        today_seconds = 0.0
        any_saved = False
        segments = self._split_by_day(start_time, end_time)

        for seg_start, seg_end in segments:
            play_minutes = (seg_end - seg_start).total_seconds() / 60
            if play_minutes >= self.min_play_minutes:
                success = self._save_to_spreadsheet(game, seg_start, seg_end)
                if success:
                    any_saved = True
                    # 当日分のみ加算
                    if seg_start.date() == today:
                        today_seconds += (seg_end - seg_start).total_seconds()
                    print(Messages.GAME_RECORDED.format(game_title=game.game_title))
                else:
                    print(f'{game.game_title}の記録保存に失敗しました')
            else:
                print(Messages.GAME_TOO_SHORT.format(
                    game_title=game.game_title,
                    min_minutes=self.min_play_minutes,
                ))

        return today_seconds if any_saved else None

    def _split_by_day(
        self,
        start: datetime,
        end: datetime,
    ) -> List[Tuple[datetime, datetime]]:
        """セッションを日付境界で分割."""
        segments: List[Tuple[datetime, datetime]] = []
        current_start = start

        while current_start.date() < end.date():
            # 当日の終わり（23:59:59.999999）
            day_end = datetime.combine(
                current_start.date(),
                time(23, 59, 59, 999999),
            )
            segments.append((current_start, day_end))
            # 翌日の開始（00:00:00）
            current_start = datetime.combine(
                current_start.date() + timedelta(days=1),
                time(0, 0, 0),
            )

        segments.append((current_start, end))
        return segments

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
        today = datetime.now().date()
        today_seconds = 0.0
        any_saved = False
        segments = self._split_by_day(start_time, end_time)

        for seg_start, seg_end in segments:
            play_minutes = (seg_end - seg_start).total_seconds() / 60
            if play_minutes >= self.min_play_minutes:
                success = self._save_to_spreadsheet(game, seg_start, seg_end)
                if success:
                    any_saved = True
                    # 当日分のみ加算
                    if seg_start.date() == today:
                        today_seconds += (seg_end - seg_start).total_seconds()
                    print(Messages.GAME_RECORDED.format(game_title=game.game_title))
                else:
                    print(f'{game.game_title}の記録保存に失敗しました')
            else:
                print(Messages.GAME_TOO_SHORT.format(
                    game_title=game.game_title,
                    min_minutes=self.min_play_minutes,
                ))

        return today_seconds if any_saved else None


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


def _format_hms(total_seconds: float) -> str:
    """秒を HH:MM:SS.F 形式に整形（Fは0.1秒単位）."""
    seconds_int = int(total_seconds)
    minutes, seconds_int = divmod(seconds_int, 60)
    hours, minutes = divmod(minutes, 60)
    fraction = int((total_seconds - int(total_seconds)) * TIME_FRACTION_PRECISION)
    return f'{hours:02}:{minutes:02}:{seconds_int:02}.{fraction}'


# =============================================================================
# ウィンドウ状態管理
# =============================================================================
class WindowState:
    """ウィンドウ状態の保存/読み込み用データクラス."""

    @staticmethod
    def load(path: Path) -> Tuple[int, int, str, Dict[str, Tuple[int, int]]]:
        """保存ファイルから(x, y, display_mode, mode_sizes)を読み込む."""
        if not path.exists():
            return (0, 0, "max", dict(MODE_DEFAULT_SIZES))
        
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            x = int(data.get("x", 0))
            y = int(data.get("y", 0))
            mode = data.get("display_mode", "max")
            
            # display_mode の検証（不正値の場合はデフォルトに戻す）
            if mode not in DISPLAY_MODES:
                mode = "max"
            
            mode_sizes: Dict[str, Tuple[int, int]] = {}
            mode_sizes_raw = data.get("mode_sizes", {})
            for key in DISPLAY_MODES:
                if key in mode_sizes_raw and isinstance(mode_sizes_raw[key], list) and len(mode_sizes_raw[key]) == 2:
                    try:
                        mode_sizes[key] = (int(mode_sizes_raw[key][0]), int(mode_sizes_raw[key][1]))
                    except (ValueError, TypeError):
                        mode_sizes[key] = MODE_DEFAULT_SIZES[key]
                else:
                    mode_sizes[key] = MODE_DEFAULT_SIZES[key]
            
            return (x, y, mode, mode_sizes)
        except (OSError, json.JSONDecodeError, ValueError):
            return (0, 0, "max", dict(MODE_DEFAULT_SIZES))
    
    @staticmethod
    def save(path: Path, x: int, y: int, display_mode: str, mode_sizes: Dict[str, Tuple[int, int]]) -> None:
        """現在の状態をファイルに保存."""
        try:
            mode_sizes_serialized = {k: [v[0], v[1]] for k, v in mode_sizes.items()}
            data = {
                "x": x,
                "y": y,
                "width": mode_sizes[display_mode][0],
                "height": mode_sizes[display_mode][1],
                "display_mode": display_mode,
                "mode_sizes": mode_sizes_serialized,
            }
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except (OSError, ValueError):
            pass


# =============================================================================
# 日次統計トラッカー
# =============================================================================
class DailyStatsTracker:
    """日付ごとの統計を追跡し、日付変更時にリセットするクラス."""

    def __init__(self, get_current_date=None) -> None:
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


# =============================================================================
# メインウィンドウ
# =============================================================================
class MainWindow(QWidget):
    """メインウィンドウ."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(BASE_TITLE)
        
        # ウィンドウ状態を読み込み
        x, y, self.display_mode, self.mode_sizes = WindowState.load(STATE_FILE)
        self.setGeometry(x, y, *self.mode_sizes[self.display_mode])

        self.w = build_main_layout(self)

        self.games: List[GameEntry] = []
        self.browsers: Sequence[str] = DEFAULT_BROWSERS
        self.scanner: WindowScanner
        self.recorder: SessionRecorder
        self.daily_stats = DailyStatsTracker()
        self.active_games_cache: List[GameEntry] = []
        self.inactive_games_cache: List[GameEntry] = []
        self.latest_window_titles: List[str] = []
        self._init_components()

        # タイマーをインスタンス変数に保持（GCによる停止防止）
        self._scan_timer = self._start_timer(POLL_INTERVAL_SECONDS, self._scan_tick)
        self._ui_timer = self._start_timer(UI_REFRESH_INTERVAL_SECONDS, self._ui_tick)

        # 初回更新
        self._scan_tick()
        self._ui_tick()

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィンドウ状態を保存."""
        self._save_window_state()
        super().closeEvent(event)

    def _start_timer(self, interval_seconds: float, callback) -> QTimer:
        """タイマーを作成して開始."""
        timer = QTimer(self)
        timer.setInterval(int(interval_seconds * 1000))
        timer.timeout.connect(callback)
        timer.start()
        return timer

    def _init_components(self) -> None:
        """設定を読み込みコンポーネントを初期化."""
        config = ConfigLoader()
        games = GameInfoLoader(config).load()
        if not games:
            self._set_status('ゲーム情報が取得できませんでした（config.ini を確認）')
            self.setDisabled(True)
            return

        self.games = games
        self.browsers = config.window_scan.get('browsers', DEFAULT_BROWSERS)
        self.scanner = WindowScanner(
            excluded_titles=(
                list(config.window_scan.get('excluded_titles', DEFAULT_EXCLUDED_TITLES))
                + [BASE_TITLE, self.windowTitle()]
            )
        )
        self.recorder = SessionRecorder(
            log_handler=LogHandler(),
            min_play_minutes=MIN_PLAY_MINUTES,
        )
        self.daily_stats.today_completed_seconds = self._load_today_completed_seconds()
        self.daily_stats.today_game_minutes_cache = self._load_today_game_minutes()
        self._apply_display_mode()
        self._apply_mode_geometry()
        self._set_status(Messages.NO_GAME_PLAYING)

    def _scan_tick(self) -> None:
        """監視サイクル（1秒間隔）."""
        if not self.games:
            return

        if self.daily_stats.check_day_change():
            # 日付変更時、UIも強制クリア
            self.w.today_games_table.setRowCount(0)
        
        window_titles = self.scanner.get_titles()
        foreground_title = self.scanner.get_foreground_title()
        active_games, inactive_games = self._update_game_states(window_titles, foreground_title)

        self.latest_window_titles = window_titles
        self.active_games_cache = active_games
        self.inactive_games_cache = inactive_games
        self._update_active_list(active_games, inactive_games)
        self._update_window_list(window_titles)

        if active_games or inactive_games:
            self._set_status('プレイ時間計測中')
        else:
            self._set_status(Messages.NO_GAME_PLAYING)

    def _update_game_states(
        self,
        window_titles: List[str],
        foreground_title: Optional[str],
    ) -> Tuple[List[GameEntry], List[GameEntry]]:
        """ゲーム状態を更新し、アクティブ/非アクティブなゲームを返す.
        
        Returns:
            (active_games, inactive_games) のタプル。
            active_games: フォアグラウンドでプレイ中のゲーム
            inactive_games: 非アクティブ状態（5分未満）のゲーム
        """
        active_games: List[GameEntry] = []
        inactive_games: List[GameEntry] = []
        
        for game in self.games:
            # ウィンドウが存在するか
            window_exists = any(
                game.matches_window(title, self.browsers)
                for title in window_titles
            )
            # フォアグラウンドか（アクティブか）
            is_foreground = (
                foreground_title is not None
                and game.matches_window(foreground_title, self.browsers)
            )
            
            if not game.is_playing:
                # プレイ中でない場合
                if is_foreground:
                    # フォアグラウンドになったら新規セッション開始
                    game.start_session()
                    active_games.append(game)
            else:
                # プレイ中の場合
                if not window_exists:
                    # ウィンドウ消失 → 記録して終了
                    recorded_seconds = self.recorder.record(game)
                    if recorded_seconds:
                        self.daily_stats.add_completed_seconds(recorded_seconds)
                        self.daily_stats.update_game_minutes_cache(self._load_today_game_minutes())
                elif is_foreground:
                    # フォアグラウンド → アクティブ状態に
                    game.set_active()
                    active_games.append(game)
                else:
                    # 非フォアグラウンドだがウィンドウは存在
                    if not game.is_inactive():
                        # 非アクティブ状態に移行
                        game.set_inactive()
                    
                    # 非アクティブ時間が5分超過したか確認
                    inactive_seconds = game.get_inactive_seconds()
                    if inactive_seconds >= INACTIVE_TIMEOUT_MINUTES * 60:
                        # 5分超過 → 非アクティブ化時点までを記録
                        if game.start_time and game.inactive_since:
                            recorded_seconds = self.recorder.record_with_times(
                                game, game.start_time, game.inactive_since
                            )
                            if recorded_seconds:
                                self.daily_stats.add_completed_seconds(recorded_seconds)
                                self.daily_stats.update_game_minutes_cache(self._load_today_game_minutes())
                        # セッション終了（ウィンドウはまだ存在するが、新規セッション待ち）
                        game.is_playing = False
                        game.start_time = None
                        game.inactive_since = None
                    else:
                        # まだ5分未満 → 非アクティブリストに追加
                        inactive_games.append(game)
        
        return active_games, inactive_games

    def _update_active_list(self, active_games: List[GameEntry], inactive_games: List[GameEntry]) -> None:
        """プレイ中ゲームリストを更新."""
        if not active_games and not inactive_games:
            self.w.active_display.setText('---')
            return
        
        parts: List[str] = []
        for game in active_games:
            parts.append(game.game_title)
        for game in inactive_games:
            parts.append(f'{game.game_title} - 停止中')
        
        self.w.active_display.setText(' / '.join(parts))

    def _update_session_times(self, active_games: List[GameEntry]) -> None:
        """現在のセッション時間を更新（最長セッションを表示）.
        
        active_games と inactive_games_cache を合わせた全プレイ中ゲームから最長を表示。
        """
        all_playing = active_games + self.inactive_games_cache
        if not all_playing:
            self.w.session_time_display.setText('---')
            return

        max_elapsed = max(
            (datetime.now() - game.start_time).total_seconds()
            if game.start_time else 0
            for game in all_playing
        )
        self.w.session_time_display.setText(_format_hms(max_elapsed))

    def _update_today_totals(self, active_games: List[GameEntry]) -> None:
        """今日のプレイ時間（完了+進行中）を更新.
        
        - 日跨ぎセッションは今日0:00以降のみカウント
        - 5分未満の進行中セッションは除外
        - 非アクティブ中のゲームも含む
        """
        total_seconds = self.daily_stats.today_completed_seconds
        now = datetime.now()
        today_start = datetime.combine(now.date(), time(0, 0, 0))
        
        all_playing = active_games + self.inactive_games_cache
        for game in all_playing:
            if game.start_time:
                # 日跨ぎの場合は今日0:00から、そうでなければ開始時刻から
                effective_start = max(game.start_time, today_start)
                elapsed_seconds = (now - effective_start).total_seconds()
                # 5分未満の進行中セッションは除外
                if elapsed_seconds >= MIN_PLAY_MINUTES * 60:
                    total_seconds += elapsed_seconds
        self.w.today_time_display.setText(_format_hms(total_seconds))

    def _update_window_list(self, window_titles: List[str]) -> None:
        """現在のウィンドウタイトルリストを更新."""
        self.w.window_list.clear()
        for title in window_titles:
            self.w.window_list.addItem(title)

    def _load_today_game_minutes(self) -> Dict[str, float]:
        """キャッシュから今日プレイしたゲームごとの分数を集計."""
        game_minutes: Dict[str, float] = {}
        today = datetime.now().date()
        try:
            records = self.recorder.log_handler.get_cached_records()
            for record in records:
                try:
                    start = datetime.strptime(str(record['start_time']), "%Y/%m/%d %H:%M:%S")
                    end = datetime.strptime(str(record['end_time']), "%Y/%m/%d %H:%M:%S")
                    game_title = str(record.get('title', '不明'))
                except (ValueError, KeyError):
                    continue
                if start.date() != today:
                    continue
                minutes = (end - start).total_seconds() / 60
                game_minutes[game_title] = game_minutes.get(game_title, 0) + minutes
        except Exception:
            pass
        return game_minutes

    def _update_today_games_list(self) -> None:
        """今日プレイしたゲームの一覧と時間を更新."""
        # キャッシュをコピー
        game_minutes = dict(self.daily_stats.today_game_minutes_cache)
        
        # 空の場合（日付変更直後など）はテーブルをクリア
        all_playing = self.active_games_cache + self.inactive_games_cache
        if not game_minutes and not all_playing:
            if self.daily_stats.last_today_games_content != "":
                self.daily_stats.last_today_games_content = ""
                self.w.today_games_table.setRowCount(0)
            return
        
        # 現在プレイ中のゲームの時間を追加（日跨ぎ対応、5分未満除外、非アクティブ含む）
        now = datetime.now()
        today_start = datetime.combine(now.date(), time(0, 0, 0))
        
        for game in all_playing:
            if game.start_time:
                # 日跨ぎの場合は今日0:00から、そうでなければ開始時刻から
                effective_start = max(game.start_time, today_start)
                current_minutes = (now - effective_start).total_seconds() / 60
                # 5分未満の進行中セッションは除外
                if current_minutes >= MIN_PLAY_MINUTES:
                    game_minutes[game.game_title] = game_minutes.get(game.game_title, 0) + current_minutes
        
        # 時間でソート（降順）
        sorted_games = sorted(game_minutes.items(), key=lambda x: x[1], reverse=True)
        
        # 内容を文字列化して比較
        content = '\n'.join(f'{game_title}: {int(minutes)}分' for game_title, minutes in sorted_games)
        
        # 内容が変わった場合のみ更新
        if content != self.daily_stats.last_today_games_content:
            self.daily_stats.last_today_games_content = content
            self.w.today_games_table.setRowCount(len(sorted_games))
            for row, (game_title, minutes) in enumerate(sorted_games):
                self.w.today_games_table.setItem(row, 0, QTableWidgetItem(game_title))
                self.w.today_games_table.setItem(row, 1, QTableWidgetItem(f'{int(minutes)}分'))

    def _load_today_completed_seconds(self) -> float:
        """起動時に今日分の完了プレイ時間をロード（キャッシュ使用）."""
        total = 0.0
        today = datetime.now().date()
        try:
            records = self.recorder.log_handler.get_cached_records()
            for record in records:
                try:
                    start = datetime.strptime(str(record['start_time']), "%Y/%m/%d %H:%M:%S")
                    end = datetime.strptime(str(record['end_time']), "%Y/%m/%d %H:%M:%S")
                except (ValueError, KeyError):
                    continue
                if start.date() != today:
                    continue
                total += (end - start).total_seconds()
        except Exception:
            # ログハンドラのエラーは無視（初回起動時など）
            pass
        return total

    def _save_window_state(self) -> None:
        """ウィンドウ位置・サイズ・表示モードを保存."""
        geom = self.geometry()
        # 現在のサイズをmode_sizesに記録
        self.mode_sizes[self.display_mode] = (geom.width(), geom.height())
        # 保存
        WindowState.save(STATE_FILE, geom.x(), geom.y(), self.display_mode, self.mode_sizes)

    def _set_status(self, message: str) -> None:
        """ステータスメッセージをタイトルバーに反映。"""
        title = f"{BASE_TITLE} - {message}" if message else BASE_TITLE
        self.setWindowTitle(title)
        if hasattr(self, "scanner"):
            self.scanner.excluded_titles.add(title)

    def _apply_mode_geometry(self) -> None:
        """表示モードに応じたサイズを適用."""
        w, h = self.mode_sizes.get(self.display_mode, MODE_DEFAULT_SIZES[self.display_mode])
        # サイズを強制適用するため、一時的に min/max を固定
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)
        self.resize(w, h)
        self.setMinimumHeight(0)
        self.setMaximumHeight(MAX_WIDGET_HEIGHT)

    def _apply_display_mode(self) -> None:
        """表示モードに応じてウィジェット表示を切り替え。"""
        is_expanded = self.display_mode != "min"  # mid/maxで表示
        is_max = self.display_mode == "max"

        # 常に表示
        self._set_widget_visibility(self.w.today_label, True)
        self._set_widget_visibility(self.w.today_time_display, True)

        # mid/maxで表示
        self._set_widget_visibility(self.w.session_label, is_expanded)
        self._set_widget_with_height(
            self.w.session_time_display,
            is_expanded,
            min_height=0,
            max_height=MAX_WIDGET_HEIGHT if is_expanded else 0
        )
        
        self._set_widget_visibility(self.w.active_label, is_expanded)
        self._set_widget_with_height(
            self.w.active_display,
            is_expanded,
            min_height=self.w.active_min_height if is_expanded else 0,
            max_height=self.w.active_max_height if is_expanded else 0
        )
        
        self._set_widget_visibility(self.w.today_games_label, is_expanded)
        self._set_widget_with_height(
            self.w.today_games_table,
            is_expanded,
            min_height=self.w.today_games_min_height if is_expanded else 0,
            max_height=MAX_WIDGET_HEIGHT if is_expanded else 0
        )

        # maxのみ表示
        self._set_widget_visibility(self.w.window_label, is_max)
        self._set_widget_with_height(
            self.w.window_list,
            is_max,
            min_height=0,
            max_height=MAX_WIDGET_HEIGHT if is_max else 0
        )
        
        self._apply_mode_geometry()

    def _set_widget_visibility(self, widget: QWidget, visible: bool) -> None:
        """ウィジェットの表示/非表示を設定."""
        widget.setVisible(visible)

    def _set_widget_with_height(self, widget: QWidget, visible: bool, *, min_height: int, max_height: int) -> None:
        """ウィジェットの表示/非表示と高さ制約を設定."""
        widget.setVisible(visible)
        widget.setMinimumHeight(min_height)
        widget.setMaximumHeight(max_height)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """クリックで表示モードをトグル。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._cycle_display_mode()
        super().mousePressEvent(event)

    def _cycle_display_mode(self) -> None:
        """表示モードを循環。"""
        idx = DISPLAY_MODES.index(self.display_mode)

        self.display_mode = DISPLAY_MODES[(idx + 1) % len(DISPLAY_MODES)]
        self._apply_display_mode()
        self._save_window_state()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """リサイズ時に現在モードのサイズを記録."""
        self.mode_sizes[self.display_mode] = (self.width(), self.height())
        super().resizeEvent(event)

    def _ui_tick(self) -> None:
        """UIだけを高速更新（0.1秒間隔）."""
        # セッション時間と今日の合計時間のみ更新（リストはスキャン時に更新）
        self._update_session_times(self.active_games_cache)
        self._update_today_totals(self.active_games_cache)
        self._update_today_games_list()


# =============================================================================
# エントリーポイント
# =============================================================================
def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
