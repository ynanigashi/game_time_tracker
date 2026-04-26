"""Play log handler backed by local SQLite with spreadsheet backup."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from src.core.reporting import (
    ReportSummary,
    TrendPoint,
    TrendSeries,
    build_game_report,
    build_play_time_trend,
    build_play_time_trend_by_title,
)
from src.core.time_utils import GSS_DATETIME_FORMAT, SECONDS_PER_MINUTE
from src.infra.config_loader import (
    LogHandlerConfig,
    PLAY_LOG_BACKUP_MODE_SPREADSHEET,
    PLAY_LOG_SYNC_CONFLICT_NEW_ID,
    PLAY_LOG_SYNC_CONFLICT_OVERWRITE,
)
from src.infra.gspread_service import GspreadService
from src.infra.play_log_store import PlayLogStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayLogSyncResult:
    """Summary of a manual play-log spreadsheet sync."""

    imported: int
    backed_up: int
    total: int


class LogHandler:
    """Handle play log reads and writes.

    SQLite is the primary store. The spreadsheet is used as a best-effort backup
    and initial import source when the local play log DB is empty.
    """

    gspread_service: Optional[GspreadService]
    records: List[Dict[str, Any]]
    index: int

    def __init__(
        self,
        config: LogHandlerConfig,
        *,
        play_log_store: Optional[PlayLogStore] = None,
    ) -> None:
        self.play_log_store = play_log_store or PlayLogStore()
        self.backup_enabled = (
            config.backup_mode == PLAY_LOG_BACKUP_MODE_SPREADSHEET
        )
        self.sync_conflict_policy = config.sync_conflict_policy
        self.gspread_service = (
            self._connect_backup_service(config) if self.backup_enabled else None
        )
        self.sync_with_spreadsheet()

    def _connect_backup_service(
        self,
        config: LogHandlerConfig,
    ) -> Optional[GspreadService]:
        try:
            return GspreadService(
                cert_file_path=config.cert_file_path,
                sheet_key=config.sheet_key,
                sheet_gid=config.sheet_gid,
            )
        except Exception as exc:
            logger.warning("spreadsheet backup is unavailable: %s", exc)
            return None

    def _fetch_backup_records(self) -> Optional[List[Dict[str, Any]]]:
        if self.gspread_service is None:
            return []
        try:
            return self.gspread_service.get_all_records()
        except Exception as exc:
            logger.warning("failed to fetch spreadsheet backup records: %s", exc)
            return None

    def _sync_backup_records(self, records: List[Dict[str, Any]]) -> int:
        pending_ids = {
            str(record["record_id"])
            for record in self.play_log_store.load_pending_backup_records()
        }
        records_to_import = [
            record
            for record in records
            if self._remote_record_id(record) not in pending_ids
        ]
        imported = self.play_log_store.import_records(records_to_import, backed_up=True)
        if imported:
            logger.info("synced %s play records from spreadsheet backup", imported)
        return imported

    @staticmethod
    def _remote_record_id(record: Dict[str, Any]) -> str:
        return str(record.get("record_id") or record.get("id") or "").strip()

    @classmethod
    def _remote_record_ids(cls, records: List[Dict[str, Any]]) -> set[str]:
        return {
            record_id
            for record in records
            if (record_id := cls._remote_record_id(record))
        }

    @staticmethod
    def _record_to_values(record: Dict[str, Any]) -> List[Any]:
        return [
            record["record_id"],
            record.get("device_id", ""),
            record["index"],
            record["start_time"],
            record["end_time"],
            record["title"],
            record.get("play_with_friends", False),
        ]

    @staticmethod
    def _record_to_legacy_values(record: Dict[str, Any]) -> List[Any]:
        return [
            record["index"],
            record["start_time"],
            record["end_time"],
            record["title"],
            record.get("play_with_friends", False),
        ]

    @staticmethod
    def _uses_legacy_backup_schema(records: List[Dict[str, Any]]) -> bool:
        if not records:
            return False
        headers = set(records[0].keys())
        return "record_id" not in headers and "No" in headers

    @classmethod
    def _record_to_backup_values(
        cls,
        record: Dict[str, Any],
        *,
        legacy_schema: bool,
    ) -> List[Any]:
        if legacy_schema:
            return cls._record_to_legacy_values(record)
        return cls._record_to_values(record)

    def _back_up_pending_records(self, remote_records: List[Dict[str, Any]]) -> int:
        if self.gspread_service is None:
            return 0
        pending_records = self.play_log_store.load_pending_backup_records()
        if not pending_records:
            return 0
        legacy_schema = self._uses_legacy_backup_schema(remote_records)
        remote_record_ids = self._remote_record_ids(remote_records)
        backed_up = 0
        for record in pending_records:
            record_id = str(record["record_id"])
            if not legacy_schema and record_id in remote_record_ids:
                if self.sync_conflict_policy == PLAY_LOG_SYNC_CONFLICT_OVERWRITE:
                    success = self.gspread_service.update_row_by_record_id(
                        record_id,
                        self._record_to_values(record),
                    )
                    if not success:
                        logger.warning(
                            "failed to update duplicated play record: %s",
                            record_id,
                        )
                        return backed_up
                    self.play_log_store.mark_backed_up(record_id)
                    backed_up += 1
                    continue
                if self.sync_conflict_policy == PLAY_LOG_SYNC_CONFLICT_NEW_ID:
                    record = self.play_log_store.reissue_record_id(record_id)
                    record_id = str(record["record_id"])
            try:
                values = self._record_to_backup_values(
                    record,
                    legacy_schema=legacy_schema,
                )
                success = self.gspread_service.append_row(values)
            except Exception as exc:
                logger.warning("failed to back up pending play record: %s", exc)
                return backed_up
            if not success:
                logger.warning(
                    "failed to back up pending play record: %s",
                    record.get("index"),
                )
                return backed_up
            self.play_log_store.mark_backed_up(str(record["record_id"]))
            remote_record_ids.add(record_id)
            backed_up += 1
        return backed_up

    def sync_with_spreadsheet(self) -> PlayLogSyncResult:
        """Pull remote play logs and push pending local records."""
        remote_records = self._fetch_backup_records()
        if remote_records is None:
            imported = 0
            backed_up = 0
        else:
            imported = self._sync_backup_records(remote_records)
            backed_up = self._back_up_pending_records(remote_records)
        self.records = self.get_all_records()
        self.index = self.play_log_store.max_index()
        return PlayLogSyncResult(
            imported=imported,
            backed_up=backed_up,
            total=len(self.records),
        )

    def get_all_records(self) -> List[Dict[str, Any]]:
        """Return locally stored play records."""
        return self.play_log_store.load_records()

    def get_and_increment_index(self) -> int:
        """Return the next local record index."""
        self.index += 1
        return self.index

    @staticmethod
    def format_datetime_to_gss_style(dt: datetime) -> str:
        """Format datetime in the spreadsheet-compatible style."""
        return dt.strftime(GSS_DATETIME_FORMAT)

    def get_cached_records(self) -> List[Dict[str, Any]]:
        """Return cached local records."""
        return self.records

    def get_today_stats(self) -> Tuple[Dict[str, float], float]:
        """Return today's play time by title and total seconds."""
        from src.core.models import parse_record

        game_minutes: Dict[str, float] = {}
        total_seconds = 0.0
        parse_failed_count = 0
        today = datetime.now().date()

        try:
            for record in self.records:
                parsed = parse_record(record)
                if parsed is None:
                    parse_failed_count += 1
                    continue
                if parsed.start.date() != today:
                    continue

                seconds = (parsed.end - parsed.start).total_seconds()
                total_seconds += seconds

                minutes = seconds / SECONDS_PER_MINUTE
                game_minutes[parsed.game_title] = (
                    game_minutes.get(parsed.game_title, 0) + minutes
                )
        except Exception as exc:
            logger.error("failed to calculate today's play stats: %s", exc)
        if parse_failed_count:
            logger.debug(
                "get_today_stats skipped invalid records (count=%s)",
                parse_failed_count,
            )

        return game_minutes, total_seconds

    def get_report_stats(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> ReportSummary:
        """Return aggregated report statistics from the local cache."""
        return build_game_report(
            self.records,
            start_date=start_date,
            end_date=end_date,
        )

    def get_trend_stats(
        self,
        *,
        granularity: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[TrendPoint]:
        """Return aggregated play-time trend points from the local cache."""
        return build_play_time_trend(
            self.records,
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
        )

    def get_trend_stats_by_title(
        self,
        *,
        granularity: str,
        titles: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[TrendSeries]:
        """Return title-grouped play-time trend points from the local cache."""
        return build_play_time_trend_by_title(
            self.records,
            granularity=granularity,
            titles=titles,
            start_date=start_date,
            end_date=end_date,
        )

    def save_record(self, values: List[Any]) -> bool:
        """Save a play record locally and back it up to the spreadsheet."""
        try:
            record = self.play_log_store.save_record(values, backed_up=False)
        except Exception as exc:
            logger.error("failed to save play record locally: %s", exc)
            return False

        self.records.append(record)
        if self.gspread_service is None:
            return True

        self.sync_with_spreadsheet()
        return True
