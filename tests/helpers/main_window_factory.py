"""Helper utilities for constructing mock MainWindow instances in tests."""

from typing import Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

from src.app import main
from src.core import adapters as services
from src.core import domain
from tests.test_stubs import FakeLogHandler


DEFAULT_MODE_SIZES: Dict[str, Tuple[int, int]] = {
    "min": (300, 80),
    "mid": (300, 200),
    "max": (300, 400),
}


def attach_window_title_stubs(window: main.MainWindow) -> None:
    """Attach getter/setter stubs for window title."""
    window._window_title = ""
    window.setWindowTitle = lambda t: setattr(window, "_window_title", t)
    window.windowTitle = lambda: window._window_title


def attach_geometry_stubs(
    window: main.MainWindow,
    *,
    x: int = 100,
    y: int = 200,
    width: int = 300,
    height: int = 200,
) -> None:
    """Attach geometry and size stubs."""
    window._geom = MagicMock()
    window._geom.x.return_value = x
    window._geom.y.return_value = y
    window._geom.width.return_value = width
    window._geom.height.return_value = height
    window.geometry = lambda: window._geom
    window.width = lambda: width
    window.height = lambda: height


def create_mock_main_window(
    *,
    browsers: Optional[List[str]] = None,
    include_state_tracker: bool = True,
    include_scanner: bool = False,
    include_latest_window_titles: bool = False,
    display_mode: Optional[str] = None,
    mode_sizes: Optional[Dict[str, Tuple[int, int]]] = None,
    include_ui: bool = True,
    today_games_rowcount_zero: bool = False,
    include_title_stubs: bool = False,
    include_geometry_stubs: bool = False,
) -> main.MainWindow:
    """Create a MainWindow test double without running MainWindow.__init__."""
    with patch.object(main.MainWindow, "__init__", lambda self: None):
        window = main.MainWindow()
    window._initialize_collaborators()

    window.games = []
    window.browsers = list(browsers or ["Chrome"])
    window.active_games_cache = []
    window.inactive_games_cache = []
    if include_latest_window_titles:
        window.latest_window_titles = []

    if display_mode is not None:
        window.display_mode = display_mode
    if mode_sizes is not None:
        window.mode_sizes = dict(mode_sizes)
    elif display_mode is not None:
        window.mode_sizes = dict(DEFAULT_MODE_SIZES)

    window.daily_stats = domain.DailyStatsTracker()
    window.overlay_window = None
    window.tray_icon = None
    window.tray_menu = None
    window._is_quitting = False
    window.startup_window_visible = False
    window.tray_overlay_enabled = False
    window.overlay_position = None
    window._overtime_alert_tracker = main.OvertimeAlertTracker(
        thresholds_minutes=main.OVERTIME_ALERT_THRESHOLDS_MINUTES,
        alerted_threshold_minutes=set(),
    )
    window._overtime_alert_toggle_connected = False
    window.overtime_alert_enabled = True
    window.recorder = services.SessionRecorder(
        log_handler=FakeLogHandler(),
        min_play_minutes=5,
    )

    if include_state_tracker:
        window.state_tracker = domain.GameStateTracker(
            recorder=window.recorder,
            daily_stats=window.daily_stats,
            browsers=list(window.browsers),
            inactive_timeout_minutes=5,
        )

    if include_ui:
        window.w = MagicMock()
        window.w.active_display = MagicMock()
        window.w.session_time_display = MagicMock()
        window.w.today_time_display = MagicMock()
        window.w.window_list = MagicMock()
        window.w.today_games_table = MagicMock()
        window.w.report_button = MagicMock()
        window.w.manual_record_button = MagicMock()
        if today_games_rowcount_zero:
            window.w.today_games_table.rowCount.return_value = 0

    if include_scanner:
        window.scanner = MagicMock()
        window.scanner.excluded_titles = set()

    if include_title_stubs:
        attach_window_title_stubs(window)
    if include_geometry_stubs:
        attach_geometry_stubs(window)

    return window
