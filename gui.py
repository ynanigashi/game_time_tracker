"""PySide6 GUI for Game Time Tracker."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QApplication, QWidget

from config_loader import DEFAULT_BROWSERS, DEFAULT_EXCLUDED_TITLES, ConfigLoader
from gui_layout import LayoutWidgets, build_main_layout
from log_handler import LogHandler
from main import (
    GameEntry,
    GameInfoLoader,
    SessionRecorder,
    WindowScanner,
    _format_elapsed,
    MIN_PLAY_MINUTES,
    POLL_INTERVAL_SECONDS,
    Messages,
)

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


def _format_hms(total_seconds: float) -> str:
    """秒を HH:MM:SS.F 形式に整形（Fは0.1秒単位）."""
    seconds_int = int(total_seconds)
    minutes, seconds_int = divmod(seconds_int, 60)
    hours, minutes = divmod(minutes, 60)
    fraction = int((total_seconds - int(total_seconds)) * TIME_FRACTION_PRECISION)
    return f'{hours:02}:{minutes:02}:{seconds_int:02}.{fraction}'


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
        self.today_completed_seconds: float = 0.0
        self.active_games_cache: List[GameEntry] = []
        self.latest_window_titles: List[str] = []
        self._init_components()

        self._start_timer(POLL_INTERVAL_SECONDS, self._scan_tick)
        self._start_timer(UI_REFRESH_INTERVAL_SECONDS, self._ui_tick)

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
        self.today_completed_seconds = self._load_today_completed_seconds()
        self._apply_display_mode()
        self._apply_mode_geometry()
        self._set_status(Messages.NO_GAME_PLAYING)

    def _scan_tick(self) -> None:
        """監視サイクル（1秒間隔）."""
        if not self.games:
            return

        window_titles = self.scanner.get_titles()
        active_games = self._update_game_states(window_titles)

        self.latest_window_titles = window_titles
        self.active_games_cache = active_games
        self._update_active_list(active_games)
        self._update_window_list(window_titles)

        if active_games:
            self._set_status('プレイ時間計測中')
        else:
            self._set_status(Messages.NO_GAME_PLAYING)

    def _update_game_states(self, window_titles: List[str]) -> List[GameEntry]:
        """ゲーム状態を更新し、アクティブなゲームを返す."""
        active_games: List[GameEntry] = []
        for game in self.games:
            detected = any(
                game.matches_window(title, self.browsers)
                for title in window_titles
            )
            if detected and not game.is_playing:
                game.start_session()
            elif not detected and game.is_playing:
                recorded_seconds = self.recorder.record(game)
                if recorded_seconds:
                    self.today_completed_seconds += recorded_seconds

            if game.is_playing:
                active_games.append(game)
        return active_games

    def _update_active_list(self, active_games: List[GameEntry]) -> None:
        """プレイ中ゲームリストを更新."""
        if not active_games:
            self.w.active_display.setText('---')
            return
        names = ' / '.join(game.game_title for game in active_games)
        self.w.active_display.setText(names)

    def _update_session_times(self, active_games: List[GameEntry]) -> None:
        """現在のセッション時間を更新（最長セッションを表示）."""
        if not active_games:
            self.w.session_time_display.setText('---')
            return

        max_elapsed = max(
            (datetime.now() - game.start_time).total_seconds()
            if game.start_time else 0
            for game in active_games
        )
        self.w.session_time_display.setText(_format_hms(max_elapsed))

    def _update_today_totals(self, active_games: List[GameEntry]) -> None:
        """今日のプレイ時間（完了+進行中）を更新."""
        total_seconds = self.today_completed_seconds
        now = datetime.now()
        for game in active_games:
            if game.start_time:
                total_seconds += (now - game.start_time).total_seconds()
        self.w.today_time_display.setText(_format_hms(total_seconds))

    def _update_window_list(self, window_titles: List[str]) -> None:
        """現在のウィンドウタイトルリストを更新."""
        self.w.window_list.clear()
        for title in window_titles:
            self.w.window_list.addItem(title)

    def _load_today_completed_seconds(self) -> float:
        """起動時に今日分の完了プレイ時間をロード."""
        total = 0.0
        today = datetime.now().date()
        try:
            records = self.recorder.log_handler.get_all_records()
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


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
