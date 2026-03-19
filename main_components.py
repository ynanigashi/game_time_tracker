"""Backward-compatible module wrapper."""

import sys as _sys

from src.app import main_components as _impl

_sys.modules[__name__] = _impl
