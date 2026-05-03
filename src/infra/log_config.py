"""Application logging configuration."""

from __future__ import annotations

import atexit
import logging
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.infra.runtime_paths import default_log_file, resolve_log_file

LOG_MAX_BYTES = 1 * 1024 * 1024
LOG_BACKUP_COUNT = 3


@dataclass
class LoggingConfigState:
    """Mutable logging configuration state."""

    configured: bool = False
    log_file_path: Path = default_log_file()
    max_bytes: int = LOG_MAX_BYTES
    backup_count: int = LOG_BACKUP_COUNT

    @property
    def log_dir(self) -> Path:
        return self.log_file_path.parent


DEFAULT_LOGGING_STATE = LoggingConfigState()


def configure_logging(state: LoggingConfigState = DEFAULT_LOGGING_STATE) -> None:
    """Initialize root logging once for application startup."""
    if state.configured:
        return

    root_logger = logging.getLogger()
    if root_logger.handlers:
        state.configured = True
        return

    state.log_file_path = resolve_log_file()
    state.log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        state.log_file_path,
        maxBytes=state.max_bytes,
        backupCount=state.backup_count,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            file_handler,
        ],
    )
    atexit.register(logging.shutdown)
    state.configured = True


def reset_logging_state(state: LoggingConfigState = DEFAULT_LOGGING_STATE) -> None:
    """Reset logging state for tests."""
    state.configured = False
    state.log_file_path = default_log_file()
