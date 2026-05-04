"""Mutable dialog references for MainWindow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DialogRefState:
    """Owns reusable dialog references and dialog button connection flags."""

    report_dialog: Optional[Any] = None
    game_catalog_dialog: Optional[Any] = None
    manual_record_dialog: Optional[Any] = None
    settings_dialog: Optional[Any] = None
    report_button_connected: bool = False
    manual_record_button_connected: bool = False
