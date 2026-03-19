"""Backward-compatible module wrapper."""

import sys as _sys

from src.infra import log_handler as _impl

_sys.modules[__name__] = _impl
