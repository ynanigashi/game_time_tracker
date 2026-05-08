"""Typed play-log records shared by local storage and backup code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple


PLAY_LOG_INDEX_KEYS: Tuple[str, ...] = ("index", "record_index", "No", "no")
PLAY_LOG_FRIENDS_KEYS: Tuple[str, ...] = ("play_with_friends", "with_friends")


def serialize_play_log_bool(value: Any) -> str:
    """Serialize bool-like values to the spreadsheet-compatible text form."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return "TRUE" if str(value).upper() == "TRUE" else "FALSE"


def deserialize_play_log_bool(value: Any) -> bool:
    """Deserialize spreadsheet/local bool values."""
    return str(value).upper() == "TRUE"


def first_present(
    record: Mapping[str, Any],
    keys: Tuple[str, ...],
    default: Any = "",
) -> Any:
    """Return the first non-empty mapping value for the requested keys."""
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def play_log_index_from_mapping(record: Mapping[str, Any]) -> int:
    """Extract the play-log index from a local or spreadsheet row."""
    index = first_present(record, PLAY_LOG_INDEX_KEYS)
    if index in (None, ""):
        raise ValueError("play record index is required")
    return int(index)


def play_log_record_id_from_mapping(record: Mapping[str, Any]) -> str:
    """Extract or derive the stable play-log record id."""
    record_id = str(record.get("record_id") or record.get("id") or "").strip()
    if record_id:
        return record_id
    return f"sheet:{play_log_index_from_mapping(record)}"


def remote_play_log_record_id(record: Mapping[str, Any]) -> str:
    """Return a remote row id without deriving a synthetic one."""
    return str(record.get("record_id") or record.get("id") or "").strip()


@dataclass(frozen=True)
class PlayLogWrite:
    """Values needed to create or update a play-log row."""

    index: int
    start_time: str
    end_time: str
    title: str
    play_with_friends: bool

    @classmethod
    def from_values(cls, values: List[Any]) -> "PlayLogWrite":
        """Build a write model from the historical positional API."""
        if len(values) < 5:
            raise ValueError("play record requires index, start, end, title, friends")
        return cls(
            index=int(values[0]),
            start_time=str(values[1]),
            end_time=str(values[2]),
            title=str(values[3]),
            play_with_friends=deserialize_play_log_bool(
                serialize_play_log_bool(values[4])
            ),
        )

    def serialized_friends(self) -> str:
        return serialize_play_log_bool(self.play_with_friends)


@dataclass(frozen=True)
class PlayLogRecord:
    """A persisted play-log row."""

    record_id: str
    device_id: str
    index: int
    start_time: str
    end_time: str
    title: str
    play_with_friends: bool

    @classmethod
    def from_mapping(
        cls,
        record: Mapping[str, Any],
        *,
        default_device_id: str = "unknown-device",
    ) -> "PlayLogRecord":
        """Build from a local dict, spreadsheet row, or sqlite row mapping."""
        return cls(
            record_id=play_log_record_id_from_mapping(record),
            device_id=str(record.get("device_id") or default_device_id),
            index=play_log_index_from_mapping(record),
            start_time=str(record["start_time"]),
            end_time=str(record["end_time"]),
            title=str(record["title"]),
            play_with_friends=deserialize_play_log_bool(
                serialize_play_log_bool(
                    first_present(record, PLAY_LOG_FRIENDS_KEYS, False)
                )
            ),
        )

    @classmethod
    def from_write(
        cls,
        write: PlayLogWrite,
        *,
        record_id: str,
        device_id: str,
    ) -> "PlayLogRecord":
        """Build a persisted record from a write model."""
        return cls(
            record_id=record_id,
            device_id=device_id,
            index=write.index,
            start_time=write.start_time,
            end_time=write.end_time,
            title=write.title,
            play_with_friends=write.play_with_friends,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return the historical dict shape used by UI/reporting code."""
        return {
            "record_id": self.record_id,
            "device_id": self.device_id,
            "index": self.index,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "title": self.title,
            "play_with_friends": self.play_with_friends,
        }

    def to_backup_values(self) -> List[Any]:
        """Return values for the current spreadsheet backup schema."""
        return [
            self.record_id,
            self.device_id,
            self.index,
            self.start_time,
            self.end_time,
            self.title,
            self.play_with_friends,
        ]

    def to_legacy_backup_values(self) -> List[Any]:
        """Return values for the legacy spreadsheet backup schema."""
        return [
            self.index,
            self.start_time,
            self.end_time,
            self.title,
            self.play_with_friends,
        ]


@dataclass(frozen=True)
class PendingPlayLogRecord:
    """A play-log row waiting for spreadsheet synchronization."""

    record: PlayLogRecord
    sync_action: str = "append"

    @property
    def record_id(self) -> str:
        return self.record.record_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.record.to_dict(),
            "_sync_action": self.sync_action,
        }
