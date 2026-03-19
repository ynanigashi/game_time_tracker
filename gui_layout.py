"""Backward-compatible module wrapper."""

import sys as _sys

from src.ui import gui_layout as _impl

_sys.modules[__name__] = _impl
