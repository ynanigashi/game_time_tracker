"""Overtime alert tracking and UI wiring."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Tuple

from PySide6.QtWidgets import QApplication

from src.core.time_utils import SECONDS_PER_MINUTE

if TYPE_CHECKING:
    from src.app.alert_state import GameAlertState

logger = logging.getLogger(__name__)


@dataclass
class OvertimeAlertTracker:
    """Tracks which overtime thresholds have already alerted."""

    thresholds_minutes: Tuple[int, ...]
    alerted_threshold_minutes: set[int]
    last_checked_seconds: float = 0.0
    initialized: bool = False

    def prime(self, total_seconds: float) -> None:
        self.last_checked_seconds = max(0.0, float(total_seconds))
        self.alerted_threshold_minutes = {
            minute
            for minute in self.thresholds_minutes
            if self.last_checked_seconds >= minute * SECONDS_PER_MINUTE
        }
        self.initialized = True

    def update(self, total_seconds: float, *, alerts_enabled: bool) -> List[int]:
        if not self.initialized:
            self.prime(total_seconds)
            return []

        previous_seconds = self.last_checked_seconds
        current_seconds = max(0.0, float(total_seconds))
        self.last_checked_seconds = current_seconds

        if not alerts_enabled:
            return []

        triggered: List[int] = []
        for minute in self.thresholds_minutes:
            if minute in self.alerted_threshold_minutes:
                continue
            threshold_seconds = minute * SECONDS_PER_MINUTE
            if previous_seconds < threshold_seconds <= current_seconds:
                self.alerted_threshold_minutes.add(minute)
                triggered.append(minute)
        return triggered


class MainWindowOvertimeAlertController:
    """Owns overtime-alert toggle and threshold notifications."""

    def __init__(self, owner: "MainWindow", state: GameAlertState) -> None:
        self.owner = owner
        self.state = state

    def is_enabled(self) -> bool:
        return bool(self.state.overtime_alert_enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.state.overtime_alert_enabled = bool(enabled)

    def get_tracker(self) -> OvertimeAlertTracker:
        return self.state.overtime_alert_tracker

    def initialize_toggle(self) -> None:
        toggle = self.owner._get_overtime_alert_toggle()
        if toggle is None:
            return

        toggle.blockSignals(True)
        toggle.setChecked(self.is_enabled())
        toggle.blockSignals(False)

        if self.state.toggle_connected:
            try:
                toggle.toggled.disconnect(self.owner._on_overtime_alert_toggled)
            except (TypeError, RuntimeError):
                pass
        toggle.toggled.connect(self.owner._on_overtime_alert_toggled)
        self.state.toggle_connected = True

    def on_toggled(self, checked: bool) -> None:
        self.set_enabled(checked)

        now = datetime.now()
        total_seconds = self.owner._get_ui_controller().calculate_today_total_seconds(
            self.owner.active_games_cache,
            self.owner.inactive_games_cache,
            now,
        )
        self.owner._prime_overtime_alert_progress(total_seconds)
        self.owner._sync_overlay()

    def prime_progress(self, total_seconds: float) -> None:
        self.get_tracker().prime(total_seconds)

    def emit_alert(self, threshold_minutes: int) -> None:
        try:
            QApplication.beep()
        except Exception:
            logger.debug("ビープ音の再生に失敗", exc_info=True)
        logger.info("プレイ時間アラート: %s分に到達しました", threshold_minutes)

    def update_alert(self, total_seconds: float) -> None:
        tracker = self.get_tracker()
        triggered_minutes = tracker.update(
            total_seconds,
            alerts_enabled=self.is_enabled(),
        )
        for minute in triggered_minutes:
            self.owner._emit_overtime_alert(minute)
