from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository, OANDA_ID
from brokerai.db.repositories.oanda_account_snapshots import OandaAccountSnapshotsRepository
from brokerai.integrations.oanda import list_accounts
from brokerai.trading.broker.sync import run_broker_sync

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OandaAccountSyncResult:
    configured: bool
    skipped_reason: str | None = None
    accounts_count: int = 0
    summary_synced: bool = False
    account_id: str | None = None
    synced_at: datetime | None = None
    cursor_before: str | None = None
    cursor_after: str | None = None
    changes_applied: dict[str, int] = field(default_factory=dict)
    repair_triggered: bool = False


def _empty_result(*, configured: bool, skipped_reason: str | None = None) -> OandaAccountSyncResult:
    return OandaAccountSyncResult(configured=configured, skipped_reason=skipped_reason)


def _from_sync_result(result) -> OandaAccountSyncResult:
    return OandaAccountSyncResult(
        configured=result.configured,
        skipped_reason=result.skipped_reason or result.error,
        summary_synced=result.summary_synced,
        account_id=result.account_id,
        synced_at=datetime.now(timezone.utc) if result.configured and not result.skipped_reason else None,
        cursor_before=result.cursor_before,
        cursor_after=result.cursor_after,
        changes_applied=dict(result.changes_applied),
        repair_triggered=result.repair_triggered,
    )


async def run_oanda_account_sync(*, force: bool = False) -> OandaAccountSyncResult:
    """Deprecated wrapper — delegates to the unified ``run_broker_sync`` orchestrator."""
    result = await run_broker_sync(
        exchange_id=OANDA_ID,
        mode="incremental",
        force=force,
        include_account_summary=True,
        fetch_live_prices=False,
    )
    return _from_sync_result(result)


async def run_oanda_accounts_list_sync() -> int:
    """Refresh accessible account list (settings / credential test only)."""
    oanda = await ExchangeConnectionsRepository().get_oanda()
    access_token = str(oanda.get("access_token") or "").strip()
    environment = str(oanda.get("environment") or "practice")
    if not access_token:
        return 0
    accounts = await list_accounts(access_token, environment)
    await OandaAccountSnapshotsRepository().upsert_accounts_snapshot(
        exchange_id=OANDA_ID,
        environment=environment,
        accounts=accounts,
        synced_at=datetime.now(timezone.utc),
    )
    return len(accounts)


async def get_cached_oanda_account_summary(
    *,
    account_id: str | None = None,
    force_sync_if_missing: bool = True,
) -> dict[str, Any] | None:
    """Return the newest cached summary for the configured (or given) account."""
    oanda = await ExchangeConnectionsRepository().get_oanda()
    resolved_account_id = account_id or str(oanda.get("account_id") or "").strip()
    if not resolved_account_id:
        return None

    repo = OandaAccountSnapshotsRepository()
    doc = await repo.get_latest_summary(account_id=resolved_account_id)
    if doc is not None:
        return OandaAccountSnapshotsRepository.public_summary(doc)

    if force_sync_if_missing:
        result = await run_oanda_account_sync(force=True)
        if result.summary_synced and result.account_id == resolved_account_id:
            doc = await repo.get_latest_summary(account_id=resolved_account_id)
            if doc is not None:
                return OandaAccountSnapshotsRepository.public_summary(doc)
    return None
