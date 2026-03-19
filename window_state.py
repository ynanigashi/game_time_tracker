"""Backward-compatible module wrapper."""

import sys as _sys

from src.core import window_state as _impl

_sys.modules[__name__] = _impl
