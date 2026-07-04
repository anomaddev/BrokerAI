from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from brokerai.integrations.oanda import (
    get_account_details,
    iter_transactions_idrange,
    list_all_trades,
    list_transactions_idrange,
    normalize_oanda_transaction,
)
from brokerai.trading.broker.event_retention import collect_protected_event_ids
from brokerai.trading.broker.models import BrokerEvent, PositionLot
from brokerai.trading.oanda_account_state import lots_from_account_details, summary_from_account

logger = logging.getLogger(__name__)

OANDA_EXCHANGE_ID = "oanda"

EventSink = Callable[[list[BrokerEvent], frozenset[str]], Awaitable[None]]


@dataclass
class OandaBootstrapResult:
    """Canonical one-time OANDA account bootstrap payload."""

    lots: list[PositionLot] = field(default_factory=list)
    events: list[BrokerEvent] = field(default_factory=list)
    last_transaction_id: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    events_streamed: bool = False


async def run_oanda_bootstrap(
    access_token: str,
    environment: str,
    account_id: str,
    *,
    exchange_id: str = OANDA_EXCHANGE_ID,
    include_closed_trades: bool = True,
    include_event_backfill: bool = True,
    event_sink: EventSink | None = None,
    extra_lot_docs_for_protection: list[dict[str, Any]] | None = None,
) -> OandaBootstrapResult:
    """Bootstrap open lots, closed history, and transaction audit trail.

    Sequence (documented in ``docs/architecture/oanda-entity-linkages.md``):

    1. ``GET /accounts/{id}`` — open trades + ``lastTransactionID``
    2. ``GET /trades?state=CLOSED`` — historical closed trades
    3. ``GET /transactions/idrange`` — full txn backfill through cursor

    When *event_sink* is provided, step 3 streams one OANDA page at a time via
    ``iter_transactions_idrange``; ``events`` in the result is empty and
  ``events_streamed`` is True.
    """
    from brokerai.trading.broker.adapters.oanda import event_from_oanda_transaction, lot_from_oanda_trade

    account, last_txn = await get_account_details(access_token, environment, account_id)
    summary = summary_from_account(account)
    open_lots = lots_from_account_details(
        account,
        exchange_id=exchange_id,
        account_id=account_id,
    )
    by_id = {lot.broker_lot_id: lot for lot in open_lots}
    counts: dict[str, int] = {"bootstrap_open_lots": len(open_lots)}

    if include_closed_trades:
        closed_trades, txn_closed = await list_all_trades(
            access_token,
            environment,
            account_id,
            state="CLOSED",
        )
        for raw in closed_trades:
            lot = lot_from_oanda_trade(raw, exchange_id=exchange_id, account_id=account_id)
            by_id[lot.broker_lot_id] = lot
        counts["bootstrap_closed_lots"] = len(closed_trades)
        if not last_txn:
            last_txn = txn_closed

    events: list[BrokerEvent] = []
    events_streamed = False
    if include_event_backfill and last_txn:
        end_id = last_txn

        def _to_events(raw_batch: list[dict[str, Any]]) -> list[BrokerEvent]:
            batch: list[BrokerEvent] = []
            for raw in raw_batch:
                normalized = normalize_oanda_transaction(raw)
                if normalized is None:
                    continue
                batch.append(
                    event_from_oanda_transaction(
                        normalized,
                        exchange_id=exchange_id,
                        account_id=account_id,
                    )
                )
            return batch

        if event_sink is not None:
            events_streamed = True
            lot_docs = [lot.to_dict() for lot in by_id.values()]
            if extra_lot_docs_for_protection:
                lot_docs.extend(extra_lot_docs_for_protection)
            protected_event_ids = collect_protected_event_ids(lot_docs)
            event_count = 0
            async for page in iter_transactions_idrange(
                access_token,
                environment,
                account_id,
                from_id="1",
                to_id=end_id,
            ):
                batch = _to_events(page)
                if not batch:
                    continue
                await event_sink(batch, protected_event_ids)
                event_count += len(batch)
            counts["bootstrap_events"] = event_count
        else:
            raw_events, _ = await list_transactions_idrange(
                access_token,
                environment,
                account_id,
                from_id="1",
                to_id=end_id,
            )
            events = _to_events(raw_events)
            counts["bootstrap_events"] = len(events)

        logger.info(
            "OANDA bootstrap — account=%s open=%d closed=%d events=%d streamed=%s cursor=%s",
            account_id,
            counts.get("bootstrap_open_lots", 0),
            counts.get("bootstrap_closed_lots", 0),
            counts.get("bootstrap_events", 0),
            events_streamed,
            last_txn,
        )

    return OandaBootstrapResult(
        lots=list(by_id.values()),
        events=events,
        last_transaction_id=last_txn,
        summary=summary,
        counts=counts,
        events_streamed=events_streamed,
    )
