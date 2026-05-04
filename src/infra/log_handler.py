"""Play log handler backed by local SQLite with spreadsheet backup."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from src.core.reporting import ReportSummary, TrendPoint, TrendSeries
from src.core.time_utils import GSS_DATETIME_FORMAT
from src.infra.config_loader import (
    LogHandlerConfig,
    PLAY_LOG_BACKUP_MODE_SPREADSHEET,
    PLAY_LOG_SYNC_CONFLICT_NEW_ID,
    PLAY_LOG_SYNC_CONFLICT_OVERWRITE,
)
from src.infra.gspread_service import GspreadService
from src.infra.play_log_backup import PlayLogBackupMixin, _PlayLogBackupResult
from src.infra.play_log_analytics import PlayLogAnalytics
from src.infra.play_log_store import PlayLogStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayLogSyncResult:
    """Summary of a manual play-log spreadsheet sync."""

    imported: int
    backed_up: int
    total: int
    remote_count: int = 0
    import_skipped: int = 0
    pending_count: int = 0
    backup_failed: int = 0
    overwritten: int = 0
    reissued: int = 0
    error_message: str = ""


@dataclass(frozen=True)
class PlayLogEditResult:
    """Summary of editing one play-log record."""

    local_updated: bool
    spreadsheet_updated: bool
    record: Optional[Dict[str, Any]] = None
    error_message: str = ""


@dataclass(frozen=True)
class PlayLogDeleteResult:
    """Summary of deleting one play-log record."""

    local_deleted: bool
    spreadsheet_deleted: bool
    record_id: str = ""
    error_message: str = ""


class LogHandler(PlayLogBackupMixin):
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
        self._backup_legacy_schema = False
        self.gspread_service = (
            self._connect_backup_service(config) if self.backup_enabled else None
        )
        self.sync_with_spreadsheet()

    def sync_with_spreadsheet(self) -> PlayLogSyncResult:
        """Pull remote play logs and push pending local records."""
        remote_records, fetch_error = self._fetch_backup_records()
        if remote_records is None:
            imported = 0
            import_skipped = 0
            pending_count = len(self.play_log_store.load_pending_backup_records())
            backup_result = _PlayLogBackupResult(
                backed_up=0,
                pending_count=pending_count,
                failed=pending_count,
                error_message=fetch_error,
            )
            remote_count = 0
        else:
            remote_count = len(remote_records)
            self._backup_legacy_schema = self._uses_legacy_backup_schema(remote_records)
            imported, import_skipped = self._sync_backup_records(remote_records)
            backup_result = self._back_up_pending_records(remote_records)
        self.records = self.get_all_records()
        self.index = self.play_log_store.max_index()
        return PlayLogSyncResult(
            imported=imported,
            backed_up=backup_result.backed_up,
            total=len(self.records),
            remote_count=remote_count,
            import_skipped=import_skipped,
            pending_count=backup_result.pending_count,
            backup_failed=backup_result.failed,
            overwritten=backup_result.overwritten,
            reissued=backup_result.reissued,
            error_message=backup_result.error_message,
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

    def _analytics(self) -> PlayLogAnalytics:
        return PlayLogAnalytics(self.records)

    def get_today_stats(self) -> Tuple[Dict[str, float], float]:
        """Return today's play time by title and total seconds."""
        return self._analytics().get_today_stats()

    def get_report_stats(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> ReportSummary:
        """Return aggregated report statistics from the local cache."""
        return self._analytics().get_report_stats(
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
        return self._analytics().get_trend_stats(
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
        return self._analytics().get_trend_stats_by_title(
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

        self._append_new_record_to_backup(record)
        return True

    def update_record(self, record_id: str, values: List[Any]) -> PlayLogEditResult:
        """Update one play record locally and in the spreadsheet backup."""
        try:
            record = self.play_log_store.update_record(
                record_id,
                values,
                backed_up=False,
                sync_action="update",
            )
        except Exception as exc:
            logger.error("failed to update play record locally: %s", exc)
            return PlayLogEditResult(
                local_updated=False,
                spreadsheet_updated=False,
                error_message=str(exc),
            )

        spreadsheet_updated = False
        error_message = ""
        if self.gspread_service is not None:
            spreadsheet_updated, error_message = self._write_edited_record_to_backup(
                record
            )
            if spreadsheet_updated:
                self.play_log_store.mark_backed_up(record_id)

        self.records = self.get_all_records()
        self.index = self.play_log_store.max_index()
        return PlayLogEditResult(
            local_updated=True,
            spreadsheet_updated=spreadsheet_updated,
            record=record,
            error_message=error_message,
        )

    def delete_record(self, record_id: str) -> PlayLogDeleteResult:
        """Delete one play record locally and from the spreadsheet backup."""
        try:
            record = self.play_log_store.delete_record(record_id)
        except Exception as exc:
            logger.error("failed to delete play record locally: %s", exc)
            return PlayLogDeleteResult(
                local_deleted=False,
                spreadsheet_deleted=False,
                record_id=record_id,
                error_message=str(exc),
            )

        spreadsheet_deleted = False
        error_message = ""
        if self.gspread_service is not None:
            try:
                spreadsheet_deleted = self._delete_backup_record(
                    record,
                    legacy_schema=self._backup_legacy_schema,
                )
                if spreadsheet_deleted:
                    self.play_log_store.mark_backed_up(record_id)
            except Exception as exc:
                logger.warning("failed to delete play record backup: %s", exc)
                error_message = str(exc)

        self.records = self.get_all_records()
        self.index = self.play_log_store.max_index()
        return PlayLogDeleteResult(
            local_deleted=True,
            spreadsheet_deleted=spreadsheet_deleted,
            record_id=record_id,
            error_message=error_message,
        )
