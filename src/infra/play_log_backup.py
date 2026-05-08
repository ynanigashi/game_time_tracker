"""Spreadsheet backup helpers for play-log sync."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.infra.config_loader import (
    LogHandlerConfig,
    PLAY_LOG_SYNC_CONFLICT_NEW_ID,
    PLAY_LOG_SYNC_CONFLICT_OVERWRITE,
)
from src.infra.gspread_service import GspreadService
from src.infra.play_log_models import PlayLogRecord, remote_play_log_record_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PlayLogBackupResult:
    backed_up: int
    pending_count: int
    failed: int = 0
    overwritten: int = 0
    reissued: int = 0
    error_message: str = ""


class PlayLogBackupMixin:
    """Spreadsheet backup implementation shared by LogHandler."""

    def _connect_backup_service(
        self,
        config: LogHandlerConfig,
    ) -> Optional[GspreadService]:
        try:
            # Keep the historical patch point src.infra.log_handler.GspreadService
            # working for tests and callers that replace the backup service.
            from src.infra import log_handler as log_handler_module

            gspread_service_cls = getattr(
                log_handler_module,
                "GspreadService",
                GspreadService,
            )
            return gspread_service_cls(
                cert_file_path=config.cert_file_path,
                sheet_key=config.sheet_key,
                sheet_gid=config.sheet_gid,
            )
        except Exception as exc:
            logger.warning("spreadsheet backup is unavailable: %s", exc)
            return None

    def _fetch_backup_records(self) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        if self.gspread_service is None:
            return [], ""
        try:
            return self.gspread_service.get_all_records(), ""
        except Exception as exc:
            logger.warning("failed to fetch spreadsheet backup records: %s", exc)
            return None, f"スプレッドシート取得に失敗: {exc}"

    def _sync_backup_records(
        self,
        records: List[Dict[str, Any]],
    ) -> Tuple[int, int]:
        pending_ids = {
            record.record_id
            for record in self.play_log_store.load_pending_backup_record_models()
        }
        records_to_import = [
            record
            for record in records
            if self._remote_record_id(record) not in pending_ids
        ]
        import_result = self.play_log_store.import_records_detailed(
            records_to_import,
            backed_up=True,
        )
        skipped_pending = len(records) - len(records_to_import)
        skipped = skipped_pending + import_result.skipped
        if import_result.imported:
            logger.info(
                "synced %s play records from spreadsheet backup",
                import_result.imported,
            )
        return import_result.imported, skipped

    @staticmethod
    def _remote_record_id(record: Dict[str, Any]) -> str:
        return remote_play_log_record_id(record)

    @classmethod
    def _remote_record_ids(cls, records: List[Dict[str, Any]]) -> set[str]:
        return {
            record_id
            for record in records
            if (record_id := cls._remote_record_id(record))
        }

    @staticmethod
    def _record_to_values(record: PlayLogRecord) -> List[Any]:
        return record.to_backup_values()

    @staticmethod
    def _record_to_legacy_values(record: PlayLogRecord) -> List[Any]:
        return record.to_legacy_backup_values()

    @staticmethod
    def _uses_legacy_backup_schema(records: List[Dict[str, Any]]) -> bool:
        if not records:
            return False
        headers = set(records[0].keys())
        return "record_id" not in headers and "No" in headers

    @classmethod
    def _record_to_backup_values(
        cls,
        record: PlayLogRecord,
        *,
        legacy_schema: bool,
    ) -> List[Any]:
        if legacy_schema:
            return cls._record_to_legacy_values(record)
        return cls._record_to_values(record)

    def _back_up_pending_records(
        self,
        remote_records: List[Dict[str, Any]],
    ) -> _PlayLogBackupResult:
        if self.gspread_service is None:
            return _PlayLogBackupResult(backed_up=0, pending_count=0)
        pending_records = self.play_log_store.load_pending_backup_record_models()
        pending_count = len(pending_records)
        if not pending_records:
            return _PlayLogBackupResult(backed_up=0, pending_count=0)
        legacy_schema = self._uses_legacy_backup_schema(remote_records)
        self._backup_legacy_schema = legacy_schema
        remote_record_ids = self._remote_record_ids(remote_records)
        backed_up = 0
        overwritten = 0
        reissued = 0
        for pending_record in pending_records:
            record = pending_record.record
            record_id = record.record_id
            sync_action = pending_record.sync_action or "append"
            if sync_action == "delete":
                try:
                    success = self._delete_backup_record(
                        record,
                        legacy_schema=legacy_schema,
                    )
                except Exception as exc:
                    logger.warning("failed to delete pending play record: %s", exc)
                    return _PlayLogBackupResult(
                        backed_up=backed_up,
                        pending_count=pending_count,
                        failed=pending_count - backed_up,
                        overwritten=overwritten,
                        reissued=reissued,
                        error_message=f"failed to delete pending play record: {exc}",
                    )
                if not success:
                    logger.warning(
                        "failed to delete pending play record: %s",
                        record_id,
                    )
                    return _PlayLogBackupResult(
                        backed_up=backed_up,
                        pending_count=pending_count,
                        failed=pending_count - backed_up,
                        overwritten=overwritten,
                        reissued=reissued,
                        error_message=f"failed to delete pending play record: {record_id}",
                    )
                self.play_log_store.mark_backed_up(record_id)
                backed_up += 1
                remote_record_ids.discard(record_id)
                continue

            if sync_action == "update":
                try:
                    success = self._update_backup_record(
                        record,
                        legacy_schema=legacy_schema,
                    )
                except Exception as exc:
                    logger.warning("failed to update pending play record: %s", exc)
                    return _PlayLogBackupResult(
                        backed_up=backed_up,
                        pending_count=pending_count,
                        failed=pending_count - backed_up,
                        overwritten=overwritten,
                        reissued=reissued,
                        error_message=f"譁ｰ譁ｰ荳ｭ繝ｭ繧ｰ縺ｮ譖ｴ譁ｰ縺ｫ螟ｱ謨・ {exc}",
                    )
                if not success:
                    success = self.gspread_service.append_row(
                        self._record_to_backup_values(
                            record,
                            legacy_schema=legacy_schema,
                        )
                    )
                if not success:
                    logger.warning(
                        "failed to update or append pending play record: %s",
                        record_id,
                    )
                    return _PlayLogBackupResult(
                        backed_up=backed_up,
                        pending_count=pending_count,
                        failed=pending_count - backed_up,
                        overwritten=overwritten,
                        reissued=reissued,
                        error_message=f"譁ｰ譁ｰ荳ｭ繝ｭ繧ｰ縺ｮ譖ｴ譁ｰ縺ｫ螟ｱ謨・ {record_id}",
                    )
                self.play_log_store.mark_backed_up(record_id)
                backed_up += 1
                overwritten += 1
                remote_record_ids.add(record_id)
                continue

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
                        return _PlayLogBackupResult(
                            backed_up=backed_up,
                            pending_count=pending_count,
                            failed=pending_count - backed_up,
                            overwritten=overwritten,
                            reissued=reissued,
                            error_message=f"重複IDの更新に失敗: {record_id}",
                        )
                    self.play_log_store.mark_backed_up(record_id)
                    backed_up += 1
                    overwritten += 1
                    continue
                if self.sync_conflict_policy == PLAY_LOG_SYNC_CONFLICT_NEW_ID:
                    record = self.play_log_store.reissue_record_id_model(record_id)
                    record_id = record.record_id
                    reissued += 1
            try:
                values = self._record_to_backup_values(
                    record,
                    legacy_schema=legacy_schema,
                )
                success = self.gspread_service.append_row(values)
            except Exception as exc:
                logger.warning("failed to back up pending play record: %s", exc)
                return _PlayLogBackupResult(
                    backed_up=backed_up,
                    pending_count=pending_count,
                    failed=pending_count - backed_up,
                    overwritten=overwritten,
                    reissued=reissued,
                    error_message=f"未バックアップログの送信に失敗: {exc}",
                )
            if not success:
                logger.warning(
                    "failed to back up pending play record: %s",
                    record.index,
                )
                return _PlayLogBackupResult(
                    backed_up=backed_up,
                    pending_count=pending_count,
                    failed=pending_count - backed_up,
                    overwritten=overwritten,
                    reissued=reissued,
                    error_message=f"未バックアップログの送信に失敗: No.{record.index}",
                )
            self.play_log_store.mark_backed_up(record.record_id)
            remote_record_ids.add(record_id)
            backed_up += 1
        return _PlayLogBackupResult(
            backed_up=backed_up,
            pending_count=pending_count,
            overwritten=overwritten,
            reissued=reissued,
        )

    def _update_backup_record(
        self,
        record: PlayLogRecord,
        *,
        legacy_schema: bool,
    ) -> bool:
        if self.gspread_service is None:
            return False
        if legacy_schema:
            return self.gspread_service.update_row_by_key(
                "No",
                str(record.index),
                self._record_to_legacy_values(record),
            )
        return self.gspread_service.update_row_by_record_id(
            record.record_id,
            self._record_to_values(record),
        )

    def _delete_backup_record(
        self,
        record: PlayLogRecord,
        *,
        legacy_schema: bool,
    ) -> bool:
        if self.gspread_service is None:
            return False
        if legacy_schema:
            return self.gspread_service.delete_row_by_key(
                "No",
                str(record.index),
            )
        return self.gspread_service.delete_row_by_record_id(record.record_id)

    def _write_edited_record_to_backup(
        self,
        record: PlayLogRecord,
    ) -> Tuple[bool, str]:
        if self.gspread_service is None:
            return False, ""
        try:
            updated = self._update_backup_record(
                record,
                legacy_schema=self._backup_legacy_schema,
            )
            if updated:
                return True, ""

            values = self._record_to_backup_values(
                record,
                legacy_schema=self._backup_legacy_schema,
            )
            appended = self.gspread_service.append_row(values)
            if appended:
                return True, ""
            return False, "spreadsheet row update failed"
        except Exception as exc:
            logger.warning("failed to update play record backup: %s", exc)
            return False, str(exc)

    def _append_new_record_to_backup(self, record: PlayLogRecord) -> Tuple[bool, str]:
        """Append a newly saved record without re-reading the whole spreadsheet."""
        if self.gspread_service is None:
            return False, ""
        try:
            values = self._record_to_backup_values(
                record,
                legacy_schema=self._backup_legacy_schema,
            )
            appended = self.gspread_service.append_row(values)
            if appended:
                self.play_log_store.mark_backed_up(record.record_id)
                return True, ""
            return False, "spreadsheet row append failed"
        except Exception as exc:
            logger.warning("failed to append play record backup: %s", exc)
            return False, str(exc)


