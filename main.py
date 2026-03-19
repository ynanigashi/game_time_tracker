"""Backward-compatible entrypoint wrapper."""

import sys as _sys

from src.app import main as _impl

if __name__ == "__main__":
    _impl.main()
else:
    _sys.modules[__name__] = _impl
