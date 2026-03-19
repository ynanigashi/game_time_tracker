"""Backward-compatible module wrapper."""

import sys as _sys

from src.infra import config_loader as _impl

_sys.modules[__name__] = _impl
