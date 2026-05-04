"""Shared composition helpers for MainWindow collaborators."""

from __future__ import annotations

from typing import Any


class MainWindowCollaborator:
    """Delegate unknown attribute access to the owning MainWindow."""

    def __init__(self, owner: object) -> None:
        object.__setattr__(self, "_owner", owner)

    def __getattribute__(self, name: str) -> Any:
        if name == "_owner" or name.startswith("__"):
            return object.__getattribute__(self, name)
        descriptor = getattr(type(self), name, None)
        if hasattr(descriptor, "__get__") and hasattr(descriptor, "__set__"):
            return object.__getattribute__(self, name)
        owner = object.__getattribute__(self, "_owner")
        owner_state_names = getattr(type(owner), "_STATE_ATTRIBUTE_NAMES", ())
        if name in owner_state_names and "_state_access" in getattr(owner, "__dict__", {}):
            return getattr(owner, name)
        owner_dict = getattr(owner, "__dict__", {})
        if name in owner_dict:
            return owner_dict[name]
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._owner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_owner":
            object.__setattr__(self, name, value)
            return
        descriptor = getattr(type(self), name, None)
        if hasattr(descriptor, "__set__"):
            object.__setattr__(self, name, value)
            return
        setattr(self._owner, name, value)
