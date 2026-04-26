"""Runtime file path helpers."""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def app_base_dir() -> Path:
    """Return the directory that owns runtime user files."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def runtime_path(*parts: str) -> Path:
    """Build a path under the app runtime base directory."""
    return app_base_dir().joinpath(*parts)


def default_log_file() -> Path:
    return runtime_path("logs", "game_time_tracker.log")


def legacy_log_file() -> Path:
    return runtime_path("game_time_tracker.log")


def default_config_file() -> Path:
    return runtime_path("config", "config.ini")


def legacy_config_file() -> Path:
    return runtime_path("config.ini")


def default_window_state_file() -> Path:
    return runtime_path("data", "window_state.txt")


def legacy_window_state_file() -> Path:
    return runtime_path("window_state.txt")


def migrate_legacy_file(legacy_path: Path, current_path: Path) -> Path:
    """Move a legacy runtime file into its current directory when needed."""
    if current_path.exists() or not legacy_path.exists():
        return current_path

    try:
        current_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.replace(current_path)
        logger.info("migrated runtime file: %s -> %s", legacy_path, current_path)
        return current_path
    except OSError as exc:
        logger.warning(
            "failed to migrate runtime file: %s -> %s (%s)",
            legacy_path,
            current_path,
            exc,
        )
        return legacy_path


def resolve_config_file() -> Path:
    return migrate_legacy_file(legacy_config_file(), default_config_file())


def resolve_log_file() -> Path:
    return migrate_legacy_file(legacy_log_file(), default_log_file())


def resolve_window_state_file() -> Path:
    return migrate_legacy_file(
        legacy_window_state_file(),
        default_window_state_file(),
    )
