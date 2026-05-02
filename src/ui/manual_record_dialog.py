"""Manual play record entry dialog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Sequence

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.models import GameEntry
from src.core.time_utils import format_hms


DATETIME_FORMAT = "%Y/%m/%d %H:%M:%S"
ELAPSED_TIMER_INTERVAL_MS = 100
DEFAULT_RECORD_DURATION = timedelta(hours=1)
ZERO_ELAPSED_TEXT = "00:00:00.0"
_ACCEPTED_DATETIME_FORMATS = (
    DATETIME_FORMAT,
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


@dataclass(frozen=True)
class ManualPlayRecord:
    """One manually entered play session."""

    game: GameEntry
    start_time: datetime
    end_time: datetime


class ManualRecordDialog(QDialog):
    """Dialog for recording a play session without window-title detection."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        on_save: Callable[[ManualPlayRecord], bool],
        games: Sequence[GameEntry] = (),
        now_provider: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__(parent)
        self._on_save = on_save
        self._now_provider = now_provider
        self._timer_started_at: Optional[datetime] = None
        self._configure_window()
        self._initialize_elapsed_timer()
        self._initialize_widgets()
        self._set_default_time_range()
        self._connect_signals()
        self._build_layout()
        self.set_games(games)

    def _configure_window(self) -> None:
        self.setWindowTitle("手入力で記録")
        self.resize(460, 260)

    def _initialize_elapsed_timer(self) -> None:
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(ELAPSED_TIMER_INTERVAL_MS)
        self._elapsed_timer.timeout.connect(self._update_elapsed_display)

    def _initialize_widgets(self) -> None:
        self.game_combo = QComboBox(self)
        self.start_time_edit = QLineEdit(self)
        self.end_time_edit = QLineEdit(self)
        self.elapsed_display = QLabel(ZERO_ELAPSED_TEXT, self)
        self.status_label = QLabel("", self)
        self.start_button = QPushButton("開始", self)
        self.stop_button = QPushButton("停止", self)
        self.save_button = QPushButton("記録", self)
        self.close_button = QPushButton("閉じる", self)
        self.stop_button.setEnabled(False)

    def _set_default_time_range(self) -> None:
        now = self._rounded_now()
        default_start = now - DEFAULT_RECORD_DURATION
        self.start_time_edit.setText(self.format_datetime(default_start))
        self.end_time_edit.setText(self.format_datetime(now))

    def _connect_signals(self) -> None:
        self.start_button.clicked.connect(self._start_timer)
        self.stop_button.clicked.connect(self._stop_timer)
        self.save_button.clicked.connect(self._save)
        self.close_button.clicked.connect(self.accept)

    def _now(self) -> datetime:
        return self._now_provider()

    def _rounded_now(self) -> datetime:
        return self._now().replace(microsecond=0)

    @staticmethod
    def format_datetime(value: datetime) -> str:
        return value.strftime(DATETIME_FORMAT)

    @staticmethod
    def parse_datetime(value: str) -> datetime:
        text = value.strip()
        for fmt in _ACCEPTED_DATETIME_FORMATS:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        raise ValueError("日時は YYYY/MM/DD HH:MM[:SS] 形式で入力してください")

    def _build_layout(self) -> None:
        form = QFormLayout()
        form.addRow("ゲーム名", self.game_combo)
        form.addRow("開始日時", self.start_time_edit)
        form.addRow("終了日時", self.end_time_edit)
        form.addRow("経過時間", self.elapsed_display)

        timer_buttons = QHBoxLayout()
        timer_buttons.addWidget(self.start_button)
        timer_buttons.addWidget(self.stop_button)
        timer_buttons.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.close_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(timer_buttons)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)
        self.setLayout(layout)

    def set_games(self, games: Sequence[GameEntry]) -> None:
        self.game_combo.clear()
        for game in games:
            self.game_combo.addItem(game.game_title, game)

    def _selected_game(self) -> Optional[GameEntry]:
        game = self.game_combo.currentData()
        return game if isinstance(game, GameEntry) else None

    def _start_timer(self) -> None:
        now = self._rounded_now()
        self._timer_started_at = now
        self.start_time_edit.setText(self.format_datetime(now))
        self.end_time_edit.setText("")
        self.elapsed_display.setText(ZERO_ELAPSED_TEXT)
        self._set_timer_running(True)
        self._elapsed_timer.start()

    def _stop_timer(self) -> None:
        if self._timer_started_at is None:
            return
        now = self._rounded_now()
        self.end_time_edit.setText(self.format_datetime(now))
        self._elapsed_timer.stop()
        self._update_elapsed_display(now=now)
        self._set_timer_running(False)

    def _set_timer_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _elapsed_seconds(self, now: datetime) -> float:
        if self._timer_started_at is None:
            return 0.0
        return max(0.0, (now - self._timer_started_at).total_seconds())

    def _set_elapsed_seconds(self, elapsed_seconds: float) -> None:
        self.elapsed_display.setText(format_hms(elapsed_seconds))

    def _copy_game_for_record(self, selected_game: GameEntry) -> GameEntry:
        return GameEntry(
            game_title=selected_game.game_title,
            window_title=selected_game.window_title,
            play_with_friends=selected_game.play_with_friends,
            is_browser_game=selected_game.is_browser_game,
            game_id=selected_game.game_id,
        )

    def _read_time_range(self) -> tuple[datetime, datetime]:
        start_time = self.parse_datetime(self.start_time_edit.text())
        end_time = self.parse_datetime(self.end_time_edit.text())
        if end_time <= start_time:
            raise ValueError("終了日時は開始日時より後にしてください")
        return start_time, end_time

    def _update_elapsed_display(self, *, now: Optional[datetime] = None) -> None:
        if self._timer_started_at is None:
            self.elapsed_display.setText(ZERO_ELAPSED_TEXT)
            return
        current = now or self._now()
        self._set_elapsed_seconds(self._elapsed_seconds(current))

    def _collect_record(self) -> ManualPlayRecord:
        selected_game = self._selected_game()
        if selected_game is None:
            raise ValueError("ゲームを選択してください")

        start_time, end_time = self._read_time_range()
        return ManualPlayRecord(
            game=self._copy_game_for_record(selected_game),
            start_time=start_time,
            end_time=end_time,
        )

    def _save(self) -> None:
        try:
            record = self._collect_record()
        except ValueError as exc:
            QMessageBox.warning(self, "手入力エラー", str(exc))
            return

        if not self._on_save(record):
            QMessageBox.warning(
                self,
                "手入力エラー",
                "記録できませんでした。5分以上のプレイ時間か確認してください。",
            )
            return

        self.status_label.setText("記録しました")
        self.accept()
