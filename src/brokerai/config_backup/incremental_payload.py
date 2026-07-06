from __future__ import annotations

from datetime import datetime
from typing import Any

from brokerai.config_backup.restore_scopes import merge_payload_sections
from brokerai.db.repositories.config_backups import (
    ConfigBackupsRepository,
    parse_created_at,
)


def extract_incremental_payload(full_snapshot: dict[str, Any], trigger: str) -> dict[str, Any]:
    """Return a scoped partial snapshot for a settings change trigger."""
    from brokerai.config_backup.restore_scopes import extract_scoped_sections

    return extract_scoped_sections(full_snapshot, trigger)


def merge_incremental(base_payload: dict[str, Any], incremental_payload: dict[str, Any]) -> dict[str, Any]:
    """Merge an incremental snapshot into a base full payload."""
    return merge_payload_sections(base_payload, incremental_payload)


async def resolve_payload_at_change(
    change_id: str,
    *,
    repo: ConfigBackupsRepository | None = None,
) -> dict[str, Any]:
    """Reconstruct the full configuration state at a change entry's point in time."""
    repository = repo or ConfigBackupsRepository()
    change = await repository.get_by_id(change_id, include_payload=True)
    if not change:
        raise ValueError(f"Backup not found: {change_id}")

    kind = str(change.get("kind") or "")
    payload_type = str(change.get("payload_type") or "")

    if kind in {"full", "manual"}:
        return dict(change.get("payload") or {})

    if kind in {"auto", "change"} and (payload_type == "full" or not payload_type):
        return dict(change.get("payload") or {})

    change_at = parse_created_at(change.get("created_at"))
    if change_at is None:
        raise ValueError(f"Invalid created_at on backup {change_id}")

    base = await _resolve_base_full_backup(change, change_at, repository)
    if base is None:
        return dict(change.get("payload") or {})

    merged = dict(base.get("payload") or {})
    base_at = parse_created_at(base.get("created_at"))
    if base_at is None:
        return merged

    intervening = await repository.list_changes_between(base_at, change_at)
    for entry in intervening:
        entry_payload = entry.get("payload")
        if isinstance(entry_payload, dict) and entry_payload:
            merged = merge_incremental(merged, entry_payload)

    return merged


async def _resolve_base_full_backup(
    change: dict[str, Any],
    change_at: datetime,
    repo: ConfigBackupsRepository,
) -> dict[str, Any] | None:
    base_id = change.get("base_backup_id")
    if base_id:
        base = await repo.get_by_id(str(base_id), include_payload=True)
        if base and _is_full_kind(base):
            return base

    return await repo.find_latest_full_before(change_at, include_payload=True)


def _is_full_kind(doc: dict[str, Any]) -> bool:
    kind = doc.get("kind")
    return kind in {"full", "manual"}
