"""Game Time Tracker - PySide6 GUI."""

import logging
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import gspread

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('game_time_tracker.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QApplication, QWidget, QTableWidgetItem

from config_loader import DEFAULT_BROWSERS, DEFAULT_EXCLUDED_TITLES, ConfigLoader, Config
from gui_layout import build_main_layout
from log_handler import LogHandler
from models import GameEntry, parse_record
from services import (
    DailyStatsTracker,
    GameInfoLoader,
    GameStateTracker,
    Messages,
    SessionRecorder,
    WindowScanner,
    MIN_PLAY_MINUTES,
    SECONDS_PER_MINUTE,
)
from time_utils import calc_today_elapsed_seconds, format_hms
from window_state import DISPLAY_MODES, MODE_DEFAULT_SIZES, WindowState


# =============================================================================
# 定数
# =============================================================================
POLL_INTERVAL_SECONDS = 1
INACTIVE_TIMEOUT_MINUTES = 5  # 非アクティブ状態でこの時間経過でセッション分割
MINUTES_PER_HOUR = 60
STATE_FILE = Path("window_state.txt")
BASE_TITLE = "Game Time Tracker"
UI_REFRESH_INTERVAL_SECONDS = 0.1
MAX_WIDGET_HEIGHT = 16777215  # Qt default max height


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
        """ウィンドウ終了時にプレイ中のゲームを記録し、状態を保存."""
        # プレイ中のゲームを記録（5分以上の場合のみ）
        for game in self.games:
            if game.is_playing and game.start_time:
                self.recorder.record(game)
        
        self._save_window_state()
        super().closeEvent(event)

    def _start_timer(self, interval_seconds: float, callback: Callable[[], None]) -> QTimer:
        """タイマーを作成して開始."""
        timer = QTimer(self)
        timer.setInterval(int(interval_seconds * 1000))
        timer.timeout.connect(callback)
        timer.start()
        return timer

    def _init_components(self) -> None:
        """設定を読み込みコンポーネントを初期化."""
        config = ConfigLoader().load()
        games = GameInfoLoader(config).load()
        if not games:
            self._set_status('ゲーム情報が取得できませんでした（config.ini を確認）')
            self.setDisabled(True)
            return

        self.games = games
        self.browsers = config.window_scan.browsers
        self.scanner = WindowScanner(
            excluded_titles=(
                list(config.window_scan.excluded_titles)
                + [BASE_TITLE, self.windowTitle()]
            )
        )
        
        # LogHandler初期化（スプレッドシート接続失敗時は記録機能を無効化）
        try:
            log_handler = LogHandler()
        except FileNotFoundError as e:
            logger.error(f'ログ用認証情報ファイルが見つかりません: {e}')
            self._set_status('認証情報ファイルが見つかりません（config.ini を確認）')
            self.setDisabled(True)
            return
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error('ログ用スプレッドシートが見つかりません。sheet_keyを確認してください。')
            self._set_status('ログ用スプレッドシートが見つかりません')
            self.setDisabled(True)
            return
        except gspread.exceptions.APIError as e:
            logger.error(f'ログ用スプレッドシートAPIエラー: {e}')
            self._set_status('スプレッドシート接続エラー')
            self.setDisabled(True)
            return
        except Exception as e:
            logger.error(f'ログハンドラーの初期化に失敗しました: {e}')
            self._set_status('ログハンドラー初期化エラー')
            self.setDisabled(True)
            return
        
        self.recorder = SessionRecorder(
            log_handler=log_handler,
            min_play_minutes=MIN_PLAY_MINUTES,
        )
        
        # GameStateTrackerを初期化
        self.state_tracker = GameStateTracker(
            recorder=self.recorder,
            daily_stats=self.daily_stats,
            browsers=list(self.browsers),
            inactive_timeout_minutes=INACTIVE_TIMEOUT_MINUTES,
        )
        
        # 今日の統計情報を1回のパースで取得
        game_minutes, completed_seconds = self.recorder.log_handler.get_today_stats()
        self.daily_stats.today_completed_seconds = completed_seconds
        self.daily_stats.today_game_minutes_cache = game_minutes
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
        
        # GameStateTrackerでゲーム状態をスキャン
        result = self.state_tracker.scan(
            games=self.games,
            window_titles=window_titles,
            foreground_title=foreground_title,
            load_today_game_minutes_callback=self._load_today_game_minutes,
        )

        self.latest_window_titles = window_titles
        self.active_games_cache = result.active_games
        self.inactive_games_cache = result.inactive_games
        self._update_active_list(result.active_games, result.inactive_games)
        self._update_window_list(window_titles)

        if result.active_games or result.inactive_games:
            self._set_status('プレイ時間計測中')
        else:
            self._set_status(Messages.NO_GAME_PLAYING)

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


    def _update_session_times(self, active_games: List[GameEntry], now: datetime) -> None:
        """現在のセッション時間を更新（最長セッションを表示）.
        
        active_games と inactive_games_cache を合わせた全プレイ中ゲームから最長を表示。
        """
        all_playing = active_games + self.inactive_games_cache
        if not all_playing:
            self.w.session_time_display.setText('---')
            return

        max_elapsed = max(
            (now - game.start_time).total_seconds()
            if game.start_time else 0
            for game in all_playing
        )
        self.w.session_time_display.setText(format_hms(max_elapsed))

    def _update_today_totals(self, active_games: List[GameEntry], now: datetime) -> None:
        """今日のプレイ時間（完了+進行中）を更新.
        
        - 日跨ぎセッションは今日0:00以降のみカウント
        - 5分未満の進行中セッションは除外
        - 非アクティブ中のゲームも含む
        """
        total_seconds = self.daily_stats.today_completed_seconds
        min_seconds = MIN_PLAY_MINUTES * SECONDS_PER_MINUTE
        
        all_playing = active_games + self.inactive_games_cache
        for game in all_playing:
            if game.start_time:
                elapsed_seconds = calc_today_elapsed_seconds(game.start_time, now)
                if elapsed_seconds >= min_seconds:
                    total_seconds += elapsed_seconds
        self.w.today_time_display.setText(format_hms(total_seconds))

    def _update_window_list(self, window_titles: List[str]) -> None:
        """現在のウィンドウタイトルリストを更新."""
        self.w.window_list.clear()
        for title in window_titles:
            self.w.window_list.addItem(title)

    def _load_today_game_minutes(self) -> Dict[str, float]:
        """キャッシュから今日プレイしたゲームごとの分数を集計."""
        try:
            game_minutes, _ = self.recorder.log_handler.get_today_stats()
            return game_minutes
        except Exception as e:
            logger.error(f'今日のゲーム時間の集計中にエラーが発生しました: {e}')
            return {}

    def _update_today_games_list(self, now: datetime) -> None:
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
        for game in all_playing:
            current_minutes = calc_today_elapsed_seconds(game.start_time, now) / SECONDS_PER_MINUTE if game.start_time else 0.0
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
        try:
            _, completed_seconds = self.recorder.log_handler.get_today_stats()
            return completed_seconds
        except Exception as e:
            logger.error(f'今日の完了プレイ時間のロード中にエラーが発生しました: {e}')
            return 0.0

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
        now = datetime.now()
        # セッション時間と今日の合計時間のみ更新（リストはスキャン時に更新）
        self._update_session_times(self.active_games_cache, now)
        self._update_today_totals(self.active_games_cache, now)
        self._update_today_games_list(now)


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
