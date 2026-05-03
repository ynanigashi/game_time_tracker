"""MainWindow UI update and display-mode controllers."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List, Sequence, Tuple

from PySide6.QtWidgets import QTableWidgetItem, QWidget

from src.app.display_modes import clamp_mode_size
from src.core.domain import DailyStatsTracker, MIN_PLAY_MINUTES
from src.core.models import GameEntry
from src.core.time_utils import (
    SECONDS_PER_MINUTE,
    calc_today_elapsed_seconds,
    format_hms,
)
from src.core.window_state import DISPLAY_MODES, MODE_DEFAULT_SIZES
from src.ui.gui_layout import LayoutWidgets


class MainWindowUiController:
    """MainWindow のUI更新ロジック."""

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
            self.w.active_display.setText("---")
            return

        parts = [game.game_title for game in active_games]
        parts.extend(f"{game.game_title} - 停止中" for game in inactive_games)
        self.w.active_display.setText(" / ".join(parts))

    def update_session_times(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> None:
        """現在のセッション時間を更新（最長セッションを表示）。"""
        all_playing = self.all_playing_games(active_games, inactive_games)
        if not all_playing:
            self.w.session_time_display.setText("---")
            return

        max_elapsed = max(
            (now - game.start_time).total_seconds()
            if game.start_time else 0
            for game in all_playing
        )
        self.w.session_time_display.setText(format_hms(max_elapsed))

    def calculate_today_total_seconds(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> float:
        """今日のプレイ時間（完了+進行中）秒数を計算する。"""
        total_seconds = self.daily_stats.today_completed_seconds
        min_seconds = MIN_PLAY_MINUTES * SECONDS_PER_MINUTE

        all_playing = self.all_playing_games(active_games, inactive_games)
        for game in all_playing:
            if game.start_time:
                elapsed_seconds = calc_today_elapsed_seconds(game.start_time, now)
                if elapsed_seconds >= min_seconds:
                    total_seconds += elapsed_seconds
        return total_seconds

    def update_today_totals(
        self,
        active_games: Sequence[GameEntry],
        inactive_games: Sequence[GameEntry],
        now: datetime,
    ) -> float:
        """今日のプレイ時間（完了+進行中）を更新."""
        total_seconds = self.calculate_today_total_seconds(
            active_games,
            inactive_games,
            now,
        )
        self.w.today_time_display.setText(format_hms(total_seconds))
        return total_seconds

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
                game_minutes[game.game_title] = game_minutes.get(
                    game.game_title,
                    0,
                ) + current_minutes

        sorted_games = sorted(game_minutes.items(), key=lambda x: x[1], reverse=True)
        content = "\n".join(
            f"{game_title}: {int(minutes)}分"
            for game_title, minutes in sorted_games
        )

        if content != self.daily_stats.last_today_games_content:
            self.daily_stats.last_today_games_content = content
            self.w.today_games_table.setRowCount(len(sorted_games))
            for row, (game_title, minutes) in enumerate(sorted_games):
                self.w.today_games_table.setItem(row, 0, QTableWidgetItem(game_title))
                self.w.today_games_table.setItem(
                    row,
                    1,
                    QTableWidgetItem(f"{int(minutes)}分"),
                )


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
        w, h = clamp_mode_size(display_mode, int(w), int(h))
        mode_sizes[display_mode] = (w, h)
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
        is_expanded = display_mode != "min"
        is_max = display_mode == "max"

        set_widget_visibility(widgets.today_label, is_expanded)
        set_widget_visibility(widgets.today_time_display, True)

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

        set_widget_visibility(widgets.window_label, is_max)
        set_widget_with_height(
            widgets.window_list,
            is_max,
            min_height=0,
            max_height=self.max_widget_height if is_max else 0,
        )

        if widgets.overtime_alert_toggle is not None:
            set_widget_visibility(widgets.overtime_alert_toggle, True)
        if widgets.report_button is not None:
            set_widget_visibility(widgets.report_button, True)
        if getattr(widgets, "manual_record_button", None) is not None:
            set_widget_visibility(widgets.manual_record_button, True)

        apply_mode_geometry()

    def next_display_mode(self, current_display_mode: str) -> str:
        """現在の表示モードから次のモードを返す."""
        idx = DISPLAY_MODES.index(current_display_mode)
        return DISPLAY_MODES[(idx + 1) % len(DISPLAY_MODES)]
