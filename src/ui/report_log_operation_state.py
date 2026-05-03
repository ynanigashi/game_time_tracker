"""Mutable async operation state for report log edits."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import QTimer


@dataclass
class ReportLogOperationState:
    """Owns executor/timer state for one async log operation at a time."""

    executor: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="play-log-edit",
        )
    )
    future: Optional[Future] = None
    timer: Optional[QTimer] = None
    finish_callback: Optional[Callable[[object], None]] = None

    def shutdown(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        self.finish_callback = None
        self.executor.shutdown(wait=False, cancel_futures=True)
