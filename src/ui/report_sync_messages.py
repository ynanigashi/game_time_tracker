"""Status message formatting for report spreadsheet sync."""

from __future__ import annotations

from typing import Callable


def sync_result_message(result: object, cached_count: Callable[[], int]) -> str:
    error_message = str(getattr(result, "error_message", "") or "")
    parts = [
        "スプシ同期一部失敗" if error_message else "スプシ同期完了",
        f"取得 {getattr(result, 'remote_count', 0)} 件",
        f"取込 {getattr(result, 'imported', 0)} 件",
        f"取込スキップ {getattr(result, 'import_skipped', 0)} 件",
        f"未送信 {getattr(result, 'pending_count', 0)} 件",
        f"バックアップ {getattr(result, 'backed_up', 0)} 件",
    ]
    backup_failed = getattr(result, "backup_failed", 0)
    if backup_failed:
        parts.append(f"バックアップ失敗 {backup_failed} 件")
    overwritten = getattr(result, "overwritten", 0)
    if overwritten:
        parts.append(f"上書き {overwritten} 件")
    reissued = getattr(result, "reissued", 0)
    if reissued:
        parts.append(f"別ID {reissued} 件")
    parts.append(f"合計 {getattr(result, 'total', cached_count())} 件")

    if error_message:
        parts.append(f"注意: {error_message}")
    return " / ".join(parts)
