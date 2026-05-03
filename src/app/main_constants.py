"""Constants used by the main application window."""

from __future__ import annotations

from typing import Tuple

from src.infra.runtime_paths import default_window_state_file

POLL_INTERVAL_SECONDS = 1
INACTIVE_TIMEOUT_MINUTES = 5
STATE_FILE = default_window_state_file()
BASE_TITLE = "Game Time Tracker"
UI_REFRESH_INTERVAL_SECONDS = 0.1
MAX_WIDGET_HEIGHT = 16777215
MAX_Z_WALK = 32
MIN_MODE_SAFE_WIDTH = 320
MIN_MODE_SAFE_HEIGHT = 110
OVERLAY_SAMPLE_RATIOS: Tuple[Tuple[float, float], ...] = (
    (0.5, 0.5),
    (0.25, 0.25),
    (0.75, 0.25),
    (0.25, 0.75),
    (0.75, 0.75),
)
OVERLAY_COVERED_POINTS_THRESHOLD = 2
OVERTIME_ALERT_THRESHOLDS_MINUTES: Tuple[int, ...] = (45, 50, 55, 58, 60)
