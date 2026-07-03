from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from brokerai.config.settings import get_settings
from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository, OANDA_ID
from brokerai.db.repositories.oanda_account_snapshots import OandaAccountSnapshotsRepository
from brokerai.integrations.oanda import get_account_summary, list_accounts

logger = logging.getLogger(__name__)

_SYNC_LOCK = asyncio.Lock()
_LAST_SUCCESSFUL_SYNC: datetime | None = None


@dataclass(frozen=True)
class OandaAccountSyncResult:
    configured: bool
    skipped_reason: str | None = None
    accounts_count: int = 0
    summary_synced: bool = False
    account_id: str | None = None
    synced_at: datetime | None = None


def _empty_result(*, configured: bool, skipped_reason: str | None = None) -> OandaAccountSyncResult:
    return OandaAccountSyncResult(configured=configured, skipped_reason=skipped_reason)


async def run_oanda_account_sync(*, force: bool = False) -> OandaAccountSyncResult:
    """Fetch OANDA accounts + active account summary and persist to MongoDB.

    Runs at most once per ``oanda_account_sync_interval_seconds`` unless *force*
    is True. Each successful sync appends a summary snapshot keyed by
    ``account_id`` so historical charts survive account switches.
    """
    global _LAST_SUCCESSFUL_SYNC

    settings = get_settings()
    interval = max(60, settings.oanda_account_sync_interval_seconds)

    if not force and _LAST_SUCCESSFUL_SYNC is not None:
        elapsed = (datetime.now(timezone.utc) - _LAST_SUCCESSFUL_SYNC).total_seconds()
        if elapsed < interval:
            return _empty_result(configured=True, skipped_reason="recent_sync")

    async with _SYNC_LOCK:
        if not force and _LAST_SUCCESSFUL_SYNC is not None:
            elapsed = (datetime.now(timezone.utc) - _LAST_SUCCESSFUL_SYNC).total_seconds()
            if elapsed < interval:
                return _empty_result(configured=True, skipped_reason="recent_sync")

        oanda = await ExchangeConnectionsRepository().get_oanda()
        access_token = str(oanda.get("access_token") or "").strip()
        account_id = str(oanda.get("account_id") or "").strip()
        environment = str(oanda.get("environment") or "practice")

        if not access_token or not account_id:
            return _empty_result(configured=False, skipped_reason="not_configured")

        synced_at = datetime.now(timezone.utc)
        repo = OandaAccountSnapshotsRepository()

        try:
            accounts = await list_accounts(access_token, environment)
        except httpx.HTTPError as exc:
            logger.warning("OANDA account list sync failed: %s", exc)
            return _empty_result(configured=True, skipped_reason="accounts_fetch_failed")

        await repo.upsert_accounts_snapshot(
            exchange_id=OANDA_ID,
            environment=environment,
            accounts=accounts,
            synced_at=synced_at,
        )

        try:
            summary = await get_account_summary(access_token, environment, account_id)
        except httpx.HTTPError as exc:
            logger.warning("OANDA account summary sync failed for %s: %s", account_id, exc)
            _LAST_SUCCESSFUL_SYNC = synced_at
            return OandaAccountSyncResult(
                configured=True,
                skipped_reason="summary_fetch_failed",
                accounts_count=len(accounts),
                summary_synced=False,
                account_id=account_id,
                synced_at=synced_at,
            )

        await repo.insert_summary_snapshot(
            exchange_id=OANDA_ID,
            account_id=account_id,
            environment=environment,
            summary=summary,
            synced_at=synced_at,
        )

        _LAST_SUCCESSFUL_SYNC = synced_at
        logger.info(
            "OANDA account sync — account=%s accounts=%d summary=ok",
            account_id,
            len(accounts),
        )
        return OandaAccountSyncResult(
            configured=True,
            accounts_count=len(accounts),
            summary_synced=True,
            account_id=account_id,
            synced_at=synced_at,
        )


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
