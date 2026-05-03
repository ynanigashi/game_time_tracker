"""Mutable state for overtime alerts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.app.controllers.overtime_alert import OvertimeAlertTracker


@dataclass
class GameAlertState:
    """Owns overtime-alert settings and threshold progress."""

    overtime_alert_enabled: bool
    overtime_alert_tracker: OvertimeAlertTracker

    @classmethod
    def create(
        cls,
        *,
        enabled: bool,
        thresholds_minutes: Sequence[int],
    ) -> "GameAlertState":
        return cls(
            overtime_alert_enabled=bool(enabled),
            overtime_alert_tracker=OvertimeAlertTracker(
                thresholds_minutes=tuple(thresholds_minutes),
                alerted_threshold_minutes=set(),
            ),
        )
