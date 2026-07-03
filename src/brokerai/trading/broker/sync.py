from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

import brokerai.trading.broker.adapters  # noqa: F401 — register adapters

from brokerai.config.settings import get_settings
from brokerai.bots.data_manager.candle_requirements import strategy_timeframe
from brokerai.db.client import get_db
from brokerai.db.repositories.broker_events import BrokerEventsRepository
from brokerai.db.repositories.broker_lots import BrokerLotsRepository, apply_candle_anchors_to_lot
from brokerai.db.repositories.broker_sync_state import BrokerSyncStateRepository
from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.trading.broker.adapters.base import get_adapter
from brokerai.trading.broker.close_reason import close_details_from_broker_events, enrich_lot_from_events
from brokerai.trading.broker.reconciliation import reconcile_cancelled_lots, reconcile_local_open_against_broker
from brokerai.trading.broker.models import PositionLot, SyncMode, SyncResult

logger = logging.getLogger(__name__)

_SYNC_LOCK = asyncio.Lock()
_LAST_SUCCESSFUL_SYNC: datetime | None = None
_strategy_timeframe_cache: dict[str, str | None] = {}


async def _strategy_timeframe_for_lot(lot: PositionLot) -> str | None:
    """Resolve chart timeframe from lot or linked strategy document."""
    if lot.timeframe:
        return lot.timeframe
    strategy_id = lot.strategy_id
    if not strategy_id:
        return None
    if strategy_id in _strategy_timeframe_cache:
        return _strategy_timeframe_cache[strategy_id]
    handle = await get_db()
    doc = await handle.db["strategies"].find_one(
        {"id": strategy_id},
        {"_id": 0, "timeframe": 1, "params": 1},
    )
    tf = strategy_timeframe(doc) if doc else None
    _strategy_timeframe_cache[strategy_id] = tf
    return tf


async def _prepare_lot_for_upsert(lot: PositionLot) -> PositionLot:
    """Fill missing candle anchor fields before persisting a synced lot."""
    tf = await _strategy_timeframe_for_lot(lot)
    return apply_candle_anchors_to_lot(lot, strategy_timeframe=tf)


def _empty_result(*, configured: bool, mode: SyncMode, skipped_reason: str | None = None) -> SyncResult:
    return SyncResult(configured=configured, mode=mode, skipped_reason=skipped_reason)


async def _resolve_oanda_credentials() -> tuple[dict[str, Any], str] | tuple[None, None]:
    oanda = await ExchangeConnectionsRepository().get_oanda()
    access_token = str(oanda.get("access_token") or "").strip()
    account_id = str(oanda.get("account_id") or "").strip()
    if not access_token or not account_id:
        return None, None
    credentials = {
        "access_token": access_token,
        "environment": str(oanda.get("environment") or "practice"),
    }
    return credentials, account_id


async def backfill_closed_lot_details(
    *,
    exchange_id: str = "oanda",
    account_id: str | None = None,
    credentials: dict[str, Any] | None = None,
    limit: int = 200,
) -> list[str]:
    """Backfill missing exit price / realized P/L from synced ``broker_events``.

    Uses MongoDB event history first. ``GET /trades/{id}`` is only attempted when
    local events are insufficient — avoiding 404s for misfiled transaction IDs.
    """
    lots_repo = BrokerLotsRepository()
    events_repo = BrokerEventsRepository()

    creds = credentials
    acct = account_id
    if acct is None or creds is None:
        resolved_creds, resolved_acct = await _resolve_oanda_credentials()
        creds = creds or resolved_creds
        acct = acct or resolved_acct

    candidates = await lots_repo.list_closed_lots_missing_close_details(limit=limit)
    backfilled_ids: list[str] = []

    for lot in candidates:
        lot_id = str(lot.get("id") or "")
        if not lot_id:
            continue

        lot_account = str(lot.get("account_id") or acct or "")
        broker_lot_id = str(lot.get("broker_lot_id") or lot.get("broker_order_id") or "")
        closing_event_ids = list(lot.get("closing_event_ids") or [])

        events: list[dict[str, Any]] = []
        if broker_lot_id and lot_account:
            events = await events_repo.list_events(
                exchange_id=exchange_id,
                account_id=lot_account,
                broker_lot_id=broker_lot_id,
            )

        details = close_details_from_broker_events(
            events,
            closing_event_ids=closing_event_ids,
            broker_lot_id=broker_lot_id or None,
        )

        misfiled_txn = False
        if not details and broker_lot_id and lot_account:
            txn_event = await events_repo.get_by_event_id(exchange_id, lot_account, broker_lot_id)
            if txn_event is not None:
                misfiled_txn = True
                related_lot_id = str(txn_event.get("broker_lot_id") or "")
                related_events = events
                if related_lot_id and related_lot_id != broker_lot_id:
                    related_events = await events_repo.list_events(
                        exchange_id=exchange_id,
                        account_id=lot_account,
                        broker_lot_id=related_lot_id,
                    )
                details = close_details_from_broker_events(
                    [txn_event, *related_events],
                    closing_event_ids=[broker_lot_id, *closing_event_ids],
                    broker_lot_id=related_lot_id or None,
                )

        exit_price = details.get("exit_price")
        realized_pl = details.get("realized_pl")
        closed_at = details.get("closed_at")

        if (
            (exit_price is None or realized_pl is None)
            and broker_lot_id
            and lot_account
            and creds
            and not misfiled_txn
        ):
            from brokerai.integrations.oanda import get_broker_trade

            token = str(creds.get("access_token") or "")
            environment = str(creds.get("environment") or "practice")
            if token:
                broker_closed = await get_broker_trade(token, environment, lot_account, broker_lot_id)
                if broker_closed is not None:
                    if exit_price is None:
                        exit_price = broker_closed.get("exit_price")
                    if realized_pl is None:
                        realized_pl = broker_closed.get("realized_pl")
                    if closed_at is None:
                        closed_at = broker_closed.get("closed_at")
                else:
                    logger.debug(
                        "Broker trade %s not found during close-details backfill",
                        broker_lot_id,
                    )

        if exit_price is None and realized_pl is None:
            continue

        updated = await lots_repo.backfill_close_details(
            lot_id,
            exit_price=exit_price,
            realized_pl=realized_pl,
            closed_at=closed_at,
        )
        if updated:
            backfilled_ids.append(lot_id)
            logger.info(
                "Backfilled close details on lot %s (broker_lot_id=%s) exit=%s pl=%s",
                lot_id,
                broker_lot_id,
                exit_price,
                realized_pl,
            )

    return backfilled_ids


async def run_broker_sync(
    *,
    exchange_id: str = "oanda",
    mode: SyncMode = "incremental",
    force: bool = False,
) -> SyncResult:
    """Exchange-agnostic broker sync orchestrator."""
    global _LAST_SUCCESSFUL_SYNC

    credentials, account_id = await _resolve_oanda_credentials()
    if credentials is None or account_id is None:
        return _empty_result(configured=False, mode=mode)

    if not force and mode == "incremental":
        settings = get_settings()
        if _LAST_SUCCESSFUL_SYNC is not None:
            elapsed = (datetime.now(timezone.utc) - _LAST_SUCCESSFUL_SYNC).total_seconds()
            if elapsed < settings.trade_sync_interval_seconds:
                return _empty_result(
                    configured=True,
                    mode=mode,
                    skipped_reason="recent_sync",
                )

    async with _SYNC_LOCK:
        if not force and mode == "incremental" and _LAST_SUCCESSFUL_SYNC is not None:
            settings = get_settings()
            elapsed = (datetime.now(timezone.utc) - _LAST_SUCCESSFUL_SYNC).total_seconds()
            if elapsed < settings.trade_sync_interval_seconds:
                return _empty_result(
                    configured=True,
                    mode=mode,
                    skipped_reason="recent_sync",
                )

        lots_repo = BrokerLotsRepository()
        events_repo = BrokerEventsRepository()
        sync_state_repo = BrokerSyncStateRepository()
        adapter = get_adapter(exchange_id)

        lots_upserted = 0
        events_upserted = 0
        lots_closed = 0
        enriched = 0

        try:
            cursor = await sync_state_repo.get_cursor(exchange_id, account_id)
            full_sync = mode == "full" or (mode == "incremental" and not cursor)

            broker_lots, last_txn_from_lots = await adapter.sync_lots(credentials, account_id)
            live_open_lots = await adapter.fetch_open_lots_with_prices(credentials, account_id)

            for lot in broker_lots:
                lot = await _prepare_lot_for_upsert(lot)
                await lots_repo.upsert_lot(lot, preserve_overlay=True)
                lots_upserted += 1

            events_result = await adapter.sync_events(
                credentials,
                account_id,
                since_cursor=cursor,
                full=full_sync,
            )
            events_upserted = await events_repo.upsert_events(events_result.events)

            events_by_lot: dict[str, list] = {}
            for event in events_result.events:
                if event.broker_lot_id:
                    events_by_lot.setdefault(event.broker_lot_id, []).append(event)

            for lot in broker_lots:
                lot_events = events_by_lot.get(lot.broker_lot_id, [])
                enriched_lot = enrich_lot_from_events(lot, lot_events)
                if enriched_lot.close_reason and enriched_lot.state == "closed":
                    enriched += 1
                enriched_lot = await _prepare_lot_for_upsert(enriched_lot)
                await lots_repo.upsert_lot(enriched_lot, preserve_overlay=True)

            lots_closed = await reconcile_local_open_against_broker(
                lots_repo,
                exchange_id=exchange_id,
                live_open_lots=live_open_lots,
            )

            lots_cancelled = await reconcile_cancelled_lots(
                lots_repo,
                exchange_id=exchange_id,
                account_id=account_id,
            )

            mismatches = await adapter.validate_exposure(credentials, account_id, broker_lots)

            new_cursor = events_result.cursor or last_txn_from_lots or cursor
            if new_cursor:
                await sync_state_repo.set_state(
                    exchange_id,
                    account_id,
                    sync_cursor=new_cursor,
                )

            backfilled_lot_ids = await backfill_closed_lot_details(
                exchange_id=exchange_id,
                account_id=account_id,
                credentials=credentials,
            )

            _LAST_SUCCESSFUL_SYNC = datetime.now(timezone.utc)
            return SyncResult(
                configured=True,
                mode=mode,
                lots_upserted=lots_upserted,
                events_upserted=events_upserted,
                lots_closed=lots_closed,
                enriched=enriched,
                backfilled=len(backfilled_lot_ids),
                backfilled_lot_ids=backfilled_lot_ids,
                exposure_mismatches=mismatches,
            )
        except httpx.HTTPError as exc:
            logger.warning("Broker sync failed for %s: %s", exchange_id, exc)
            return SyncResult(
                configured=True,
                mode=mode,
                error=str(exc),
            )


__all__ = ["backfill_closed_lot_details", "run_broker_sync"]
