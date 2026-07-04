from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from brokerai.config.settings import get_settings
from brokerai.db.repositories.broker_sync_state import BrokerSyncStateRepository
from brokerai.integrations.oanda import list_transactions_since, normalize_oanda_transaction
from brokerai.trading.broker.models import BrokerEvent

logger = logging.getLogger(__name__)


def as_utc_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def repair_transaction_gap(
    *,
    access_token: str,
    environment: str,
    account_id: str,
    exchange_id: str,
    since_cursor: str,
) -> list[BrokerEvent]:
    """Backfill transactions after a detected cursor gap (return only; caller persists)."""
    from brokerai.trading.broker.adapters.oanda import event_from_oanda_transaction

    logger.warning("OANDA cursor repair — account=%s since=%s", account_id, since_cursor)
    repaired, _ = await list_transactions_since(
        access_token,
        environment,
        account_id,
        since_id=since_cursor,
    )
    events: list[BrokerEvent] = []
    for raw in repaired:
        normalized = normalize_oanda_transaction(raw)
        if normalized is None:
            continue
        events.append(
            event_from_oanda_transaction(
                normalized,
                exchange_id=exchange_id,
                account_id=account_id,
            )
        )
    return events


async def repair_stale_cursor_if_needed(
    *,
    access_token: str,
    environment: str,
    account_id: str,
    exchange_id: str,
    cursor: str | None,
    sync_state_repo: BrokerSyncStateRepository,
    synced_at: datetime,
) -> tuple[str | None, bool, list[BrokerEvent]]:
    """Replay transactions when the stored cursor has not advanced for too long.

    Returns ``(cursor, repair_triggered, events)``. Events are returned only;
    ``run_broker_sync`` is the sole persistence point.
    """
    from brokerai.trading.broker.adapters.oanda import event_from_oanda_transaction

    if not cursor:
        return cursor, False, []

    settings = get_settings()
    state_doc = await sync_state_repo.get_state(exchange_id, account_id)
    last_sync_at = as_utc_aware(state_doc.get("last_sync_at") if state_doc else None)
    stale_threshold = max(300, settings.oanda_cursor_stale_threshold_seconds)
    if (
        not last_sync_at
        or (synced_at - last_sync_at).total_seconds() <= stale_threshold
    ):
        return cursor, False, []

    logger.warning(
        "OANDA stale cursor repair — account=%s last_sync=%s",
        account_id,
        last_sync_at.isoformat(),
    )
    repaired, repair_cursor = await list_transactions_since(
        access_token,
        environment,
        account_id,
        since_id=cursor,
    )
    events: list[BrokerEvent] = []
    for raw in repaired:
        normalized = normalize_oanda_transaction(raw)
        if normalized is None:
            continue
        events.append(
            event_from_oanda_transaction(
                normalized,
                exchange_id=exchange_id,
                account_id=account_id,
            )
        )
    updated_cursor = repair_cursor or cursor
    return updated_cursor, True, events


async def persist_account_summary_snapshot(
    *,
    account_id: str,
    environment: str,
    exchange_id: str,
    summary: dict[str, Any],
    synced_at: datetime,
    previous_summary: dict[str, Any] | None = None,
    force: bool = False,
) -> bool:
    """Insert a summary snapshot when values changed (or *force*)."""
    from brokerai.db.repositories.oanda_account_snapshots import (
        OandaAccountSnapshotsRepository,
        SUMMARY_FIELDS,
    )

    if not force and previous_summary is not None:
        unchanged = all(
            previous_summary.get(field) == summary.get(field) for field in SUMMARY_FIELDS
        )
        if unchanged:
            return False

    await OandaAccountSnapshotsRepository().insert_summary_snapshot(
        exchange_id=exchange_id,
        account_id=account_id,
        environment=environment,
        summary=summary,
        synced_at=synced_at,
    )
    return True
