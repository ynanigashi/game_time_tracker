"""Game Time Tracker - PySide6 GUI."""

import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, TypeVar, cast

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
from gui_layout import LayoutWidgets, build_main_layout
from log_handler import LogHandler
from models import GameEntry
from services import (
    DailyStatsTracker,
    GameInfoLoader,
    ScanResult,
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
STATE_FILE = Path("window_state.txt")
BASE_TITLE = "Game Time Tracker"
UI_REFRESH_INTERVAL_SECONDS = 0.1
MAX_WIDGET_HEIGHT = 16777215  # Qt default max height
TDependency = TypeVar("TDependency")


class MainWindowUiController:
    """MainWindow の UI 更新専用ロジック."""

    def __init__(self, widgets: LayoutWidgets, daily_stats: DailyStatsTracker) -> None:
        self.w = widgets
        self.daily_stats = daily_stats

    @staticmethod
    def all_playing_games(
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> List[GameEntry]:
        """アクティブ/非アクティブを統合したプレイ中ゲーム一覧を返す."""
        return list(active_games) + list(inactive_games)

    def update_active_list(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> None:
        """プレイ中ゲームリストを更新."""
        if not active_games and not inactive_games:
            self.w.active_display.setText('---')
            return

        parts = [game.game_title for game in active_games]
        parts.extend(f'{game.game_title} - 停止中' for game in inactive_games)
        self.w.active_display.setText(' / '.join(parts))

    def update_session_times(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> None:
        """現在のセッション時間を更新（最長セッションを表示）。"""
        all_playing = self.all_playing_games(active_games, inactive_games)
        if not all_playing:
            self.w.session_time_display.setText('---')
            return

        max_elapsed = max(
            (now - game.start_time).total_seconds()
            if game.start_time else 0
            for game in all_playing
        )
        self.w.session_time_display.setText(format_hms(max_elapsed))

    def update_today_totals(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> None:
        """今日のプレイ時間（完了+進行中）を更新."""
        total_seconds = self.daily_stats.today_completed_seconds
        min_seconds = MIN_PLAY_MINUTES * SECONDS_PER_MINUTE

        all_playing = self.all_playing_games(active_games, inactive_games)
        for game in all_playing:
            if game.start_time:
                elapsed_seconds = calc_today_elapsed_seconds(game.start_time, now)
                if elapsed_seconds >= min_seconds:
                    total_seconds += elapsed_seconds
        self.w.today_time_display.setText(format_hms(total_seconds))

    def update_window_list(self, window_titles: Sequence[str]) -> None:
        """現在のウィンドウタイトルリストを更新."""
        self.w.window_list.clear()
        for title in window_titles:
            self.w.window_list.addItem(title)

    def update_today_games_list(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> None:
        """今日プレイしたゲームの一覧と時間を更新."""
        game_minutes = dict(self.daily_stats.today_game_minutes_cache)
        all_playing = self.all_playing_games(active_games, inactive_games)

        if not game_minutes and not all_playing:
            if self.daily_stats.last_today_games_content != "":
                self.daily_stats.last_today_games_content = ""
                self.w.today_games_table.setRowCount(0)
            return

        for game in all_playing:
            current_minutes = (
                calc_today_elapsed_seconds(game.start_time, now) / SECONDS_PER_MINUTE
                if game.start_time else 0.0
            )
            if current_minutes >= MIN_PLAY_MINUTES:
                game_minutes[game.game_title] = game_minutes.get(game.game_title, 0) + current_minutes

        sorted_games = sorted(game_minutes.items(), key=lambda x: x[1], reverse=True)
        content = '\n'.join(f'{game_title}: {int(minutes)}分' for game_title, minutes in sorted_games)

        if content != self.daily_stats.last_today_games_content:
            self.daily_stats.last_today_games_content = content
            self.w.today_games_table.setRowCount(len(sorted_games))
            for row, (game_title, minutes) in enumerate(sorted_games):
                self.w.today_games_table.setItem(row, 0, QTableWidgetItem(game_title))
                self.w.today_games_table.setItem(row, 1, QTableWidgetItem(f'{int(minutes)}分'))


class MainWindowDisplayController:
    """MainWindow の表示モード制御ロジック."""

    def __init__(self, max_widget_height: int) -> None:
        self.max_widget_height = max_widget_height

    def set_widget_visibility(self, widget: QWidget, visible: bool) -> None:
        """ウィジェットの表示/非表示を設定."""
        widget.setVisible(visible)

    def set_widget_with_height(
        self,
        widget: QWidget,
        visible: bool,
        *,
        min_height: int,
        max_height: int,
    ) -> None:
        """ウィジェットの表示/非表示と高さ制約を設定."""
        widget.setVisible(visible)
        widget.setMinimumHeight(min_height)
        widget.setMaximumHeight(max_height)

    def apply_mode_geometry(
        self,
        window: QWidget,
        display_mode: str,
        mode_sizes: Dict[str, Tuple[int, int]],
    ) -> None:
        """表示モードに応じたサイズを適用."""
        w, h = mode_sizes.get(display_mode, MODE_DEFAULT_SIZES[display_mode])
        # サイズを強制適用するため、一時的に min/max を固定
        window.setMinimumHeight(h)
        window.setMaximumHeight(h)
        window.resize(w, h)
        window.setMinimumHeight(0)
        window.setMaximumHeight(self.max_widget_height)

    def apply_display_mode(
        self,
        *,
        display_mode: str,
        widgets: LayoutWidgets,
        set_widget_visibility: Callable[[QWidget, bool], None],
        set_widget_with_height: Callable[..., None],
        apply_mode_geometry: Callable[[], None],
    ) -> None:
        """表示モードに応じてウィジェット表示を切り替え."""
        is_expanded = display_mode != "min"  # mid/maxで表示
        is_max = display_mode == "max"

        # 常に表示
        set_widget_visibility(widgets.today_label, True)
        set_widget_visibility(widgets.today_time_display, True)

        # mid/maxで表示
        set_widget_visibility(widgets.session_label, is_expanded)
        set_widget_with_height(
            widgets.session_time_display,
            is_expanded,
            min_height=0,
            max_height=self.max_widget_height if is_expanded else 0,
        )

        set_widget_visibility(widgets.active_label, is_expanded)
        set_widget_with_height(
            widgets.active_display,
            is_expanded,
            min_height=widgets.active_min_height if is_expanded else 0,
            max_height=widgets.active_max_height if is_expanded else 0,
        )

        set_widget_visibility(widgets.today_games_label, is_expanded)
        set_widget_with_height(
            widgets.today_games_table,
            is_expanded,
            min_height=widgets.today_games_min_height if is_expanded else 0,
            max_height=self.max_widget_height if is_expanded else 0,
        )

        # maxのみ表示
        set_widget_visibility(widgets.window_label, is_max)
        set_widget_with_height(
            widgets.window_list,
            is_max,
            min_height=0,
            max_height=self.max_widget_height if is_max else 0,
        )

        apply_mode_geometry()

    def next_display_mode(self, current_display_mode: str) -> str:
        """現在の表示モードから次のモードを返す."""
        idx = DISPLAY_MODES.index(current_display_mode)
        return DISPLAY_MODES[(idx + 1) % len(DISPLAY_MODES)]


class MainWindowStateController:
    """MainWindow の状態読み書きロジック."""

    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file

    def load(self) -> Tuple[int, int, str, Dict[str, Tuple[int, int]]]:
        """永続化されたウィンドウ状態を読み込む."""
        return WindowState.load(self.state_file)

    def save(
        self,
        geom: object,
        display_mode: str,
        mode_sizes: Dict[str, Tuple[int, int]],
    ) -> None:
        """現在状態を mode_sizes に反映して永続化."""
        mode_sizes[display_mode] = (geom.width(), geom.height())
        WindowState.save(self.state_file, geom.x(), geom.y(), display_mode, mode_sizes)

    @staticmethod
    def record_resize(
        mode_sizes: Dict[str, Tuple[int, int]],
        display_mode: str,
        width: int,
        height: int,
    ) -> None:
        """リサイズ後サイズを mode_sizes に反映."""
        mode_sizes[display_mode] = (width, height)


class MainWindowLoopController:
    """MainWindow のタイマー起動と tick オーケストレーション."""

    def start_timer(
        self,
        owner: QWidget,
        interval_seconds: float,
        callback: Callable[[], None],
    ) -> QTimer:
        """タイマーを作成して開始."""
        timer = QTimer(owner)
        timer.setInterval(int(interval_seconds * 1000))
        timer.timeout.connect(callback)
        timer.start()
        return timer

    def run_scan_tick(self, window: "MainWindow") -> None:
        """監視サイクル（1秒間隔）."""
        if not window.games:
            return

        if window.daily_stats.check_day_change():
            # 日付変更時、UIも強制クリア
            window.w.today_games_table.setRowCount(0)

        window_titles = window.scanner.get_titles()
        foreground_title = window.scanner.get_foreground_title()
        result = window._scan_games(window_titles, foreground_title)
        window._apply_scan_result(window_titles, result)

    def run_ui_tick(self, window: "MainWindow") -> None:
        """UIだけを高速更新（0.1秒間隔）."""
        now = datetime.now()
        # セッション時間と今日の合計時間のみ更新（リストはスキャン時に更新）
        window._update_session_times(window.active_games_cache, now)
        window._update_today_totals(window.active_games_cache, now)
        window._update_today_games_list(now)


class NoGamesConfiguredError(Exception):
    """ゲーム情報が1件も読み込めなかったことを示す例外."""


@dataclass
class MainWindowBootstrapResult:
    """MainWindow の初期化に必要な依存と初期データ."""

    games: List[GameEntry]
    browsers: Sequence[str]
    scanner: WindowScanner
    recorder: SessionRecorder
    state_tracker: GameStateTracker
    today_game_minutes: Dict[str, float]
    today_completed_seconds: float


class MainWindowBootstrapError(Exception):
    """MainWindow 初期化でユーザー向けに扱う例外."""

    def __init__(self, status_message: str, log_message: Optional[str] = None) -> None:
        super().__init__(status_message)
        self.status_message = status_message
        self.log_message = log_message


class MainWindowBootstrapper:
    """MainWindow の依存構築・初期データ読み込みを担当."""

    def __init__(
        self,
        *,
        base_title: str,
        min_play_minutes: int,
        inactive_timeout_minutes: int,
        daily_stats: DailyStatsTracker,
    ) -> None:
        self.base_title = base_title
        self.min_play_minutes = min_play_minutes
        self.inactive_timeout_minutes = inactive_timeout_minutes
        self.daily_stats = daily_stats

    def bootstrap(self, *, window_title: str) -> MainWindowBootstrapResult:
        """設定・サービス・初期統計をまとめて構築する."""
        try:
            config = ConfigLoader().load()
            games = GameInfoLoader(config).load()
            if not games:
                raise NoGamesConfiguredError

            browsers = config.window_scan.browsers
            scanner = WindowScanner(
                excluded_titles=(
                    list(config.window_scan.excluded_titles)
                    + [self.base_title, window_title]
                )
            )

            log_handler = LogHandler()
            recorder = SessionRecorder(
                log_handler=log_handler,
                min_play_minutes=self.min_play_minutes,
            )
            state_tracker = GameStateTracker(
                recorder=recorder,
                daily_stats=self.daily_stats,
                browsers=list(browsers),
                inactive_timeout_minutes=self.inactive_timeout_minutes,
            )
            today_game_minutes, today_completed_seconds = recorder.log_handler.get_today_stats()

            return MainWindowBootstrapResult(
                games=games,
                browsers=browsers,
                scanner=scanner,
                recorder=recorder,
                state_tracker=state_tracker,
                today_game_minutes=today_game_minutes,
                today_completed_seconds=today_completed_seconds,
            )
        except NoGamesConfiguredError as e:
            raise MainWindowBootstrapError(
                'ゲーム情報が取得できませんでした（config.ini を確認）'
            ) from e
        except FileNotFoundError as e:
            raise MainWindowBootstrapError(
                '認証情報ファイルが見つかりません（config.ini を確認）',
                f'ログ用認証情報ファイルが見つかりません: {e}',
            ) from e
        except gspread.exceptions.SpreadsheetNotFound as e:
            raise MainWindowBootstrapError(
                'ログ用スプレッドシートが見つかりません',
                'ログ用スプレッドシートが見つかりません。sheet_keyを確認してください。',
            ) from e
        except gspread.exceptions.APIError as e:
            raise MainWindowBootstrapError(
                'スプレッドシート接続エラー',
                f'ログ用スプレッドシートAPIエラー: {e}',
            ) from e
        except Exception as e:
            raise MainWindowBootstrapError(
                'ログハンドラー初期化エラー',
                f'ログハンドラーの初期化に失敗しました: {e}',
            ) from e


# =============================================================================
# メインウィンドウ
# =============================================================================
class MainWindow(QWidget):
    """メインウィンドウ."""

    def __init__(self) -> None:
        super().__init__()
        self._initialize_window_state()
        self.w = build_main_layout(self)
        self._initialize_runtime_state()
        self._warmup_dependencies()
        self._init_components()
        self._start_background_timers()
        self._run_initial_refresh()

    def _initialize_window_state(self) -> None:
        """タイトルと永続化されたウィンドウ状態を初期適用する."""
        self.setWindowTitle(BASE_TITLE)
        x, y, self.display_mode, self.mode_sizes = self._get_state_controller().load()
        self.setGeometry(x, y, *self.mode_sizes[self.display_mode])

    def _initialize_runtime_state(self) -> None:
        """実行時状態の初期値を設定する."""
        self.games: List[GameEntry] = []
        self.browsers: Sequence[str] = DEFAULT_BROWSERS
        self.scanner: WindowScanner
        self.recorder: SessionRecorder
        self.daily_stats = DailyStatsTracker()
        self.active_games_cache: List[GameEntry] = []
        self.inactive_games_cache: List[GameEntry] = []
        self.latest_window_titles: List[str] = []

    def _warmup_dependencies(self) -> None:
        """起動直後に使う依存を事前生成する."""
        self._get_ui_controller()
        self._get_display_controller()
        self._get_loop_controller()
        self._get_bootstrapper()

    def _start_background_timers(self) -> None:
        """バックグラウンド更新タイマーを開始する."""
        # タイマーをインスタンス変数に保持（GCによる停止防止）
        self._scan_timer = self._start_timer(POLL_INTERVAL_SECONDS, self._scan_tick)
        self._ui_timer = self._start_timer(UI_REFRESH_INTERVAL_SECONDS, self._ui_tick)

    def _run_initial_refresh(self) -> None:
        """起動直後の初回描画を実行する."""
        self._scan_tick()
        self._ui_tick()

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィンドウ終了時にプレイ中のゲームを記録し、状態を保存."""
        self._record_playing_games_before_close()
        self._save_window_state()
        super().closeEvent(event)

    def _record_playing_games_before_close(self) -> None:
        """終了時に記録対象のプレイ中ゲームを記録する."""
        for game in self._iter_recordable_games():
            self.recorder.record(game)

    def _iter_recordable_games(self) -> Sequence[GameEntry]:
        """終了時に記録対象となるゲームを返す."""
        return [
            game
            for game in getattr(self, "games", [])
            if game.is_playing and game.start_time
        ]

    def _start_timer(self, interval_seconds: float, callback: Callable[[], None]) -> QTimer:
        """タイマーを作成して開始."""
        return self._get_loop_controller().start_timer(self, interval_seconds, callback)

    def _disable_with_status(self, message: str) -> None:
        """ステータスを表示してUIを無効化."""
        self._set_status(message)
        self.setDisabled(True)

    def _ensure_daily_stats(self) -> DailyStatsTracker:
        """daily_stats を必ず返す."""
        daily_stats = getattr(self, "daily_stats", None)
        if daily_stats is None:
            daily_stats = DailyStatsTracker()
            self.daily_stats = daily_stats
        return daily_stats

    def _resolve_dependency(
        self,
        attr_name: str,
        *,
        factory: Callable[[], TDependency],
        validator: Optional[Callable[[TDependency], bool]] = None,
    ) -> TDependency:
        """キャッシュ済み依存を再利用し、必要時のみ再生成する."""
        dependency = cast(Optional[TDependency], getattr(self, attr_name, None))
        if dependency is None or (validator is not None and not validator(dependency)):
            dependency = factory()
            setattr(self, attr_name, dependency)
        return dependency

    def _get_bootstrapper(self) -> MainWindowBootstrapper:
        """初期化ブートストラッパーを返す."""
        daily_stats = self._ensure_daily_stats()
        return self._resolve_dependency(
            "_bootstrapper",
            factory=lambda: MainWindowBootstrapper(
                base_title=BASE_TITLE,
                min_play_minutes=MIN_PLAY_MINUTES,
                inactive_timeout_minutes=INACTIVE_TIMEOUT_MINUTES,
                daily_stats=daily_stats,
            ),
            validator=lambda bootstrapper: bootstrapper.daily_stats is daily_stats,
        )

    def _apply_bootstrap_result(self, result: MainWindowBootstrapResult) -> None:
        """ブートストラップ結果を MainWindow の状態へ反映."""
        self.games = result.games
        self.browsers = result.browsers
        self.scanner = result.scanner
        self.recorder = result.recorder
        self.state_tracker = result.state_tracker
        self.daily_stats.today_game_minutes_cache = result.today_game_minutes
        self.daily_stats.today_completed_seconds = result.today_completed_seconds

    def _get_ui_controller(self) -> MainWindowUiController:
        """現在の widget / stats に同期した UI コントローラーを返す."""
        daily_stats = self._ensure_daily_stats()
        return self._resolve_dependency(
            "_ui_controller",
            factory=lambda: MainWindowUiController(self.w, daily_stats),
            validator=lambda controller: (
                controller.w is self.w
                and controller.daily_stats is daily_stats
            ),
        )

    def _get_display_controller(self) -> MainWindowDisplayController:
        """表示モード制御コントローラーを返す."""
        return self._resolve_dependency(
            "_display_controller",
            factory=lambda: MainWindowDisplayController(MAX_WIDGET_HEIGHT),
        )

    def _get_state_controller(self) -> MainWindowStateController:
        """状態保存コントローラーを返す."""
        return self._resolve_dependency(
            "_state_controller",
            factory=lambda: MainWindowStateController(STATE_FILE),
        )

    def _get_loop_controller(self) -> MainWindowLoopController:
        """tick/タイマー制御コントローラーを返す."""
        return self._resolve_dependency(
            "_loop_controller",
            factory=MainWindowLoopController,
        )

    def _init_components(self) -> None:
        """設定を読み込みコンポーネントを初期化."""
        try:
            result = self._get_bootstrapper().bootstrap(window_title=self.windowTitle())
        except MainWindowBootstrapError as e:
            if e.log_message:
                logger.error(e.log_message)
            self._disable_with_status(e.status_message)
            return

        self._apply_bootstrap_result(result)
        self._apply_display_mode()
        self._apply_mode_geometry()
        self._set_status(Messages.NO_GAME_PLAYING)

    def _scan_tick(self) -> None:
        """監視サイクル（1秒間隔）."""
        self._get_loop_controller().run_scan_tick(self)

    def _scan_games(self, window_titles: List[str], foreground_title: Optional[str]) -> ScanResult:
        """GameStateTracker にゲーム状態スキャンを委譲."""
        return self.state_tracker.scan(
            games=self.games,
            window_titles=window_titles,
            foreground_title=foreground_title,
            load_today_game_minutes_callback=self._load_today_game_minutes,
        )

    def _apply_scan_result(self, window_titles: List[str], result: ScanResult) -> None:
        """スキャン結果をキャッシュと UI に反映."""
        self.latest_window_titles = window_titles
        self.active_games_cache = result.active_games
        self.inactive_games_cache = result.inactive_games
        self._update_active_list(result.active_games, result.inactive_games)
        self._update_window_list(window_titles)
        self._update_scan_status(result.active_games, result.inactive_games)

    def _update_scan_status(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
    ) -> None:
        """スキャン結果に応じてステータスメッセージを更新."""
        if active_games or inactive_games:
            self._set_status('プレイ時間計測中')
        else:
            self._set_status(Messages.NO_GAME_PLAYING)

    def _update_active_list(self, active_games: List[GameEntry], inactive_games: List[GameEntry]) -> None:
        """プレイ中ゲームリストを更新."""
        self._get_ui_controller().update_active_list(active_games, inactive_games)

    def _all_playing_games(self, active_games: Optional[Sequence[GameEntry]] = None) -> List[GameEntry]:
        """アクティブ/非アクティブを統合した、現在プレイ中のゲーム一覧を返す."""
        active = active_games if active_games is not None else self.active_games_cache
        return self._get_ui_controller().all_playing_games(active, self.inactive_games_cache)


    def _update_session_times(self, active_games: List[GameEntry], now: datetime) -> None:
        """現在のセッション時間を更新（最長セッションを表示）.
        
        active_games と inactive_games_cache を合わせた全プレイ中ゲームから最長を表示。
        """
        self._get_ui_controller().update_session_times(
            active_games,
            self.inactive_games_cache,
            now,
        )

    def _update_today_totals(self, active_games: List[GameEntry], now: datetime) -> None:
        """今日のプレイ時間（完了+進行中）を更新.
        
        - 日跨ぎセッションは今日0:00以降のみカウント
        - 5分未満の進行中セッションは除外
        - 非アクティブ中のゲームも含む
        """
        self._get_ui_controller().update_today_totals(
            active_games,
            self.inactive_games_cache,
            now,
        )

    def _update_window_list(self, window_titles: List[str]) -> None:
        """現在のウィンドウタイトルリストを更新."""
        self._get_ui_controller().update_window_list(window_titles)

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
        self._get_ui_controller().update_today_games_list(
            self.active_games_cache,
            self.inactive_games_cache,
            now,
        )

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
        self._get_state_controller().save(
            self.geometry(),
            self.display_mode,
            self.mode_sizes,
        )

    def _set_status(self, message: str) -> None:
        """ステータスメッセージをタイトルバーに反映。"""
        title = f"{BASE_TITLE} - {message}" if message else BASE_TITLE
        self.setWindowTitle(title)
        if hasattr(self, "scanner"):
            self.scanner.excluded_titles.add(title)

    def _apply_mode_geometry(self) -> None:
        """表示モードに応じたサイズを適用."""
        self._get_display_controller().apply_mode_geometry(
            self,
            self.display_mode,
            self.mode_sizes,
        )

    def _apply_display_mode(self) -> None:
        """表示モードに応じてウィジェット表示を切り替え。"""
        self._get_display_controller().apply_display_mode(
            display_mode=self.display_mode,
            widgets=self.w,
            set_widget_visibility=self._set_widget_visibility,
            set_widget_with_height=self._set_widget_with_height,
            apply_mode_geometry=self._apply_mode_geometry,
        )

    def _set_widget_visibility(self, widget: QWidget, visible: bool) -> None:
        """ウィジェットの表示/非表示を設定."""
        self._get_display_controller().set_widget_visibility(widget, visible)

    def _set_widget_with_height(self, widget: QWidget, visible: bool, *, min_height: int, max_height: int) -> None:
        """ウィジェットの表示/非表示と高さ制約を設定."""
        self._get_display_controller().set_widget_with_height(
            widget,
            visible,
            min_height=min_height,
            max_height=max_height,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """クリックで表示モードをトグル。"""
        if self._should_cycle_display_mode(event):
            self._cycle_display_mode()
        super().mousePressEvent(event)

    @staticmethod
    def _should_cycle_display_mode(event: QMouseEvent) -> bool:
        """表示モード切り替え対象のクリックかを判定."""
        return event.button() == Qt.MouseButton.LeftButton

    def _cycle_display_mode(self) -> None:
        """表示モードを循環。"""
        self.display_mode = self._get_display_controller().next_display_mode(self.display_mode)
        self._apply_display_mode()
        self._save_window_state()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """リサイズ時に現在モードのサイズを記録."""
        self._record_current_mode_size()
        super().resizeEvent(event)

    def _record_current_mode_size(self) -> None:
        """現在の表示モードに対応するサイズを保存する."""
        self._get_state_controller().record_resize(
            self.mode_sizes,
            self.display_mode,
            self.width(),
            self.height(),
        )

    def _ui_tick(self) -> None:
        """UIだけを高速更新（0.1秒間隔）."""
        self._get_loop_controller().run_ui_tick(self)


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
