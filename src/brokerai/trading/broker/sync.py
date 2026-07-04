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
from brokerai.db.repositories.broker_events import BrokerEventsRepository, broker_event_from_doc
from brokerai.db.repositories.broker_lots import BrokerLotsRepository, apply_candle_anchors_to_lot
from brokerai.db.repositories.broker_sync_state import BrokerSyncStateRepository
from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.db.repositories.instrument_exposure import InstrumentExposureRepository
from brokerai.db.repositories.oanda_account_snapshots import OandaAccountSnapshotsRepository
from brokerai.trading.broker.adapters.base import get_adapter
from brokerai.trading.broker.child_orders import apply_child_orders_from_events
from brokerai.trading.broker.close_reason import close_details_from_broker_events, enrich_lot_from_events
from brokerai.trading.broker.reconciliation import reconcile_cancelled_lots, reconcile_local_open_against_broker
from brokerai.trading.broker.models import BrokerEvent, PositionLot, SyncEventsResult, SyncMode, SyncResult
from brokerai.trading.broker.event_retention import (
    collect_protected_event_ids,
    log_retention_dry_run,
)
from brokerai.trading.oanda_account_state import apply_account_state
from brokerai.trading.oanda_bootstrap import run_oanda_bootstrap
from brokerai.trading.oanda_cursor_repair import (
    persist_account_summary_snapshot,
    repair_stale_cursor_if_needed,
)

logger = logging.getLogger(__name__)

_SYNC_LOCK = asyncio.Lock()


def _merge_sync_events(
    primary: list[BrokerEvent],
    extra: list[BrokerEvent],
) -> list[BrokerEvent]:
    """Merge event batches deduplicating by ``broker_event_id``."""
    if not extra:
        return list(primary)
    seen = {event.broker_event_id for event in primary}
    merged = list(primary)
    for event in extra:
        if event.broker_event_id in seen:
            continue
        merged.append(event)
        seen.add(event.broker_event_id)
    return merged
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


async def _should_run_exposure_check(
    sync_state_repo: BrokerSyncStateRepository,
    exchange_id: str,
    account_id: str,
    *,
    full_sync: bool,
) -> bool:
    if full_sync:
        return True
    settings = get_settings()
    interval = max(60, settings.oanda_exposure_check_interval_seconds)
    state_doc = await sync_state_repo.get_state(exchange_id, account_id)
    last_check = state_doc.get("last_exposure_check_at") if state_doc else None
    if last_check is None:
        return True
    if isinstance(last_check, datetime):
        if last_check.tzinfo is None:
            last_check = last_check.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_check.astimezone(timezone.utc)).total_seconds()
        return elapsed >= interval
    return True


async def _persist_summary_from_poll_state(
    *,
    poll_state: dict[str, Any],
    account_id: str,
    environment: str,
    exchange_id: str,
    synced_at: datetime,
) -> bool:
    snapshots_repo = OandaAccountSnapshotsRepository()
    previous_summary_doc = await snapshots_repo.get_latest_summary(account_id=account_id)
    previous_summary = (
        OandaAccountSnapshotsRepository.public_summary(previous_summary_doc)
        if previous_summary_doc
        else None
    )
    state_applied = apply_account_state(poll_state, previous_summary=previous_summary)
    merged_summary = {**(previous_summary or {}), **state_applied.summary}
    return await persist_account_summary_snapshot(
        account_id=account_id,
        environment=environment,
        exchange_id=exchange_id,
        summary=merged_summary,
        synced_at=synced_at,
        previous_summary=previous_summary,
    )


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
        broker_lot_id = str(lot.get("broker_lot_id") or "")
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
    include_account_summary: bool = True,
    fetch_live_prices: bool = False,
) -> SyncResult:
    """Unified OANDA broker sync orchestrator (lots, events, summary, reconciliation)."""
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
        repair_triggered = False
        summary_synced = False
        changes_applied: dict[str, int] = {}
        environment = str(credentials.get("environment") or "practice")
        synced_at = datetime.now(timezone.utc)
        cursor_before = await sync_state_repo.get_cursor(exchange_id, account_id)

        lock_acquired = await sync_state_repo.try_acquire_sync_lock(
            exchange_id,
            account_id,
            ttl_seconds=get_settings().trade_sync_interval_seconds + 30,
        )
        if not lock_acquired:
            return _empty_result(configured=True, mode=mode, skipped_reason="lock_held")

        try:
            if await sync_state_repo.needs_environment_reset(
                exchange_id, account_id, environment=environment
            ):
                await sync_state_repo.reset_state(exchange_id, account_id)
                cursor_before = None

            cursor_before, stale_repair, stale_repair_events = await repair_stale_cursor_if_needed(
                access_token=str(credentials.get("access_token") or ""),
                environment=environment,
                account_id=account_id,
                exchange_id=exchange_id,
                cursor=cursor_before,
                sync_state_repo=sync_state_repo,
                synced_at=synced_at,
            )
            repair_triggered = repair_triggered or stale_repair

            state_doc = await sync_state_repo.get_state(exchange_id, account_id)
            needs_bootstrap = (
                mode == "full"
                or not cursor_before
                or not (state_doc or {}).get("account_bootstrap_at")
            )

            broker_lots: list[PositionLot] = []
            live_open_lots: list[PositionLot] = []
            events_result: SyncEventsResult
            last_txn_from_lots: str | None = None
            bootstrap_events_streamed = False
            bootstrap_streamed_event_count = 0

            if needs_bootstrap:
                open_lot_docs_pre = await lots_repo.list_open_lots(exchange_id=exchange_id)
                extra_lot_docs = [
                    doc
                    for doc in open_lot_docs_pre
                    if str(doc.get("account_id") or "") in ("", account_id)
                ]

                async def bootstrap_event_sink(
                    batch: list[BrokerEvent],
                    protected: frozenset[str],
                ) -> None:
                    nonlocal bootstrap_streamed_event_count
                    bootstrap_streamed_event_count += await events_repo.upsert_events(
                        batch,
                        protected_event_ids=protected,
                    )

                bootstrap = await run_oanda_bootstrap(
                    str(credentials.get("access_token") or ""),
                    environment,
                    account_id,
                    exchange_id=exchange_id,
                    event_sink=bootstrap_event_sink,
                    extra_lot_docs_for_protection=extra_lot_docs,
                )
                bootstrap_events_streamed = bootstrap.events_streamed
                broker_lots = bootstrap.lots
                events_result = SyncEventsResult(
                    events=bootstrap.events,
                    cursor=bootstrap.last_transaction_id,
                    last_event_id=(
                        bootstrap.events[-1].broker_event_id if bootstrap.events else None
                    ),
                )
                last_txn_from_lots = bootstrap.last_transaction_id
                live_open_lots = [lot for lot in broker_lots if lot.state == "open"]
                changes_applied = dict(bootstrap.counts)
                if include_account_summary and bootstrap.summary:
                    summary_synced = await persist_account_summary_snapshot(
                        account_id=account_id,
                        environment=environment,
                        exchange_id=exchange_id,
                        summary=bootstrap.summary,
                        synced_at=synced_at,
                        force=True,
                    )
            elif hasattr(adapter, "sync_incremental_from_changes") and cursor_before:
                poll_result = await adapter.sync_incremental_from_changes(
                    credentials,
                    account_id,
                    since_cursor=cursor_before,
                )
                broker_lots = poll_result.lots
                live_open_lots = poll_result.live_open_lots
                repair_triggered = repair_triggered or poll_result.repair_triggered
                events_result = SyncEventsResult(
                    events=poll_result.events,
                    cursor=poll_result.cursor,
                    last_event_id=(
                        poll_result.events[-1].broker_event_id if poll_result.events else None
                    ),
                )
                if poll_result.repair_triggered:
                    logger.warning("Broker incremental sync triggered cursor repair")
                if include_account_summary and poll_result.poll_state:
                    summary_synced = await _persist_summary_from_poll_state(
                        poll_state=poll_result.poll_state,
                        account_id=account_id,
                        environment=environment,
                        exchange_id=exchange_id,
                        synced_at=synced_at,
                    )
            else:
                return SyncResult(
                    configured=True,
                    mode=mode,
                    skipped_reason="no_cursor",
                    account_id=account_id,
                )

            if fetch_live_prices and not live_open_lots:
                live_open_lots = await adapter.fetch_open_lots_with_prices(credentials, account_id)
            elif fetch_live_prices and hasattr(adapter, "fetch_open_lots_with_prices"):
                priced = await adapter.fetch_open_lots_with_prices(credentials, account_id)
                if priced:
                    live_open_lots = priced

            events_to_persist = _merge_sync_events(events_result.events, stale_repair_events)

            lot_docs_for_retention = [lot.to_dict() for lot in broker_lots]
            open_lot_docs = await lots_repo.list_open_lots(exchange_id=exchange_id)
            for doc in open_lot_docs:
                if str(doc.get("account_id") or "") in ("", account_id):
                    lot_docs_for_retention.append(doc)
            protected_event_ids = collect_protected_event_ids(lot_docs_for_retention)
            if not bootstrap_events_streamed:
                log_retention_dry_run(events_to_persist, protected_event_ids)
            elif stale_repair_events:
                log_retention_dry_run(stale_repair_events, protected_event_ids)

            for lot in broker_lots:
                lot = await _prepare_lot_for_upsert(lot)
                await lots_repo.upsert_lot(lot, preserve_overlay=True)
                lots_upserted += 1

            if bootstrap_events_streamed:
                events_upserted = bootstrap_streamed_event_count
                if stale_repair_events:
                    events_upserted += await events_repo.upsert_events(
                        stale_repair_events,
                        protected_event_ids=protected_event_ids,
                    )
            else:
                events_upserted = await events_repo.upsert_events(
                    events_to_persist,
                    protected_event_ids=protected_event_ids,
                )

            events_by_lot: dict[str, list[BrokerEvent]] = {}
            if bootstrap_events_streamed:
                for lot in broker_lots:
                    lot_event_docs = await events_repo.list_events_for_lot(
                        exchange_id=exchange_id,
                        account_id=account_id,
                        broker_lot_id=lot.broker_lot_id,
                    )
                    if lot_event_docs:
                        events_by_lot[lot.broker_lot_id] = [
                            broker_event_from_doc(doc) for doc in lot_event_docs
                        ]
            else:
                for event in events_to_persist:
                    if event.broker_lot_id:
                        events_by_lot.setdefault(event.broker_lot_id, []).append(event)

            for lot in broker_lots:
                lot_events = events_by_lot.get(lot.broker_lot_id, [])
                enriched_lot = enrich_lot_from_events(lot, lot_events)
                enriched_lot = apply_child_orders_from_events(enriched_lot, lot_events)
                if enriched_lot.close_reason and enriched_lot.state == "closed":
                    enriched += 1
                enriched_lot = await _prepare_lot_for_upsert(enriched_lot)
                await lots_repo.upsert_lot(enriched_lot, preserve_overlay=True)

            if live_open_lots:
                lots_closed = await reconcile_local_open_against_broker(
                    lots_repo,
                    exchange_id=exchange_id,
                    live_open_lots=live_open_lots,
                )

            await reconcile_cancelled_lots(
                lots_repo,
                exchange_id=exchange_id,
                account_id=account_id,
            )

            mismatches: list = []
            exposure_check_ran = False
            if await _should_run_exposure_check(
                sync_state_repo,
                exchange_id,
                account_id,
                full_sync=needs_bootstrap,
            ):
                exposure_check_ran = True
                mismatches = await adapter.validate_exposure(credentials, account_id, broker_lots)
                if mismatches:
                    logger.warning(
                        "OANDA exposure mismatch — account=%s mismatches=%d %s",
                        account_id,
                        len(mismatches),
                        [m.to_dict() for m in mismatches],
                    )

            new_cursor = events_result.cursor or last_txn_from_lots or cursor_before
            if new_cursor:
                await sync_state_repo.set_state(
                    exchange_id,
                    account_id,
                    sync_cursor=new_cursor,
                    environment=environment,
                    account_bootstrap_at=synced_at if needs_bootstrap else None,
                    clear_last_sync_error=True,
                    last_exposure_check_at=synced_at if exposure_check_ran else None,
                )

            backfilled_lot_ids = await backfill_closed_lot_details(
                exchange_id=exchange_id,
                account_id=account_id,
                credentials=credentials,
            )

            open_lot_docs = await lots_repo.list_open_lots(exchange_id=exchange_id)
            account_open_lots = [
                doc for doc in open_lot_docs if str(doc.get("account_id") or "") == account_id
            ]
            await InstrumentExposureRepository().recompute_for_account(
                exchange_id=exchange_id,
                account_id=account_id,
                open_lots=account_open_lots,
            )

            _LAST_SUCCESSFUL_SYNC = synced_at
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
                summary_synced=summary_synced,
                repair_triggered=repair_triggered,
                account_id=account_id,
                cursor_before=cursor_before,
                cursor_after=new_cursor,
                changes_applied=changes_applied,
            )
        except httpx.HTTPError as exc:
            logger.warning("Broker sync failed for %s: %s", exchange_id, exc)
            await sync_state_repo.set_state(
                exchange_id,
                account_id,
                last_sync_error=str(exc),
            )
            return SyncResult(
                configured=True,
                mode=mode,
                error=str(exc),
                account_id=account_id,
            )
        finally:
            await sync_state_repo.release_sync_lock(exchange_id, account_id)


__all__ = ["backfill_closed_lot_details", "run_broker_sync"]
