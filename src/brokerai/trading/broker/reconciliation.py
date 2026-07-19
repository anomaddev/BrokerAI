from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BrokerLotRow
from brokerai.db.repositories.broker_lots import BrokerLotsRepository, _effective_qty, _lot_last_modified, _resolve_lot_state
from brokerai.trading.broker.models import PositionLot

logger = logging.getLogger(__name__)


def _local_broker_id(doc: dict[str, Any]) -> str:
    return str(doc.get("broker_lot_id") or "")


def _pair_direction_key(doc: dict[str, Any] | PositionLot) -> tuple[str, str]:
    if isinstance(doc, PositionLot):
        pair = doc.pair.replace("_", "/").upper()
        direction = doc.direction.lower()
    else:
        pair = str(doc.get("pair") or "").replace("_", "/").upper()
        direction = str(doc.get("direction") or "").lower()
    return pair, direction


async def reconcile_local_open_against_broker(
    lots_repo: BrokerLotsRepository,
    *,
    exchange_id: str,
    live_open_lots: list[PositionLot],
) -> int:
    """Close local open lots that are no longer open on the broker.

    Handles stale broker IDs, duplicate ``broker_lot_id`` rows (e.g. empty
    ``account_id`` from pre-sync placement), and extra locals for the same pair.
    """
    live_ids = {lot.broker_lot_id for lot in live_open_lots if lot.broker_lot_id}
    live_by_pair = {_pair_direction_key(lot): lot.broker_lot_id for lot in live_open_lots}
    live_pairs = set(live_by_pair.keys())
    closed = 0

    local_open = await lots_repo.list_open_lots(exchange_id=exchange_id, dedupe=False)

    if not live_open_lots and local_open:
        logger.warning(
            "Skipping broker reconciliation — live open lots empty but %d local open lot(s) remain",
            len(local_open),
        )
        return 0

    for local in local_open:
        if _resolve_lot_state(local) == "open" and _effective_qty(local) == 0:
            await lots_repo.close_lot(str(local.get("id")), reason="broker_closed")
            closed += 1

    if closed:
        local_open = await lots_repo.list_open_lots(exchange_id=exchange_id, dedupe=False)

    for local in local_open:
        broker_id = _local_broker_id(local)
        if broker_id and broker_id not in live_ids:
            await lots_repo.close_lot(str(local.get("id")), reason="broker_closed")
            closed += 1

    if closed:
        local_open = await lots_repo.list_open_lots(exchange_id=exchange_id, dedupe=False)

    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for local in local_open:
        by_pair.setdefault(_pair_direction_key(local), []).append(local)

    for key, group in by_pair.items():
        if key not in live_pairs:
            for local in group:
                await lots_repo.close_lot(str(local.get("id")), reason="broker_closed")
                closed += 1
            continue

        if len(group) <= 1:
            continue

        live_broker_id = live_by_pair[key]

        def rank(local: dict[str, Any]) -> tuple[int, int, float]:
            broker_id = _local_broker_id(local)
            matches_live = broker_id == live_broker_id
            on_broker = broker_id in live_ids
            return (int(matches_live), int(on_broker), _lot_last_modified(local).timestamp())

        group.sort(key=rank, reverse=True)
        for stale in group[1:]:
            await lots_repo.close_lot(str(stale.get("id")), reason="broker_closed")
            closed += 1

    return closed


async def reconcile_cancelled_lots(
    lots_repo: BrokerLotsRepository,
    *,
    exchange_id: str,
    account_id: str | None = None,
) -> int:
    """Mark local lots cancelled when broker events show the order never filled.

    Only updates rows without ``raw_broker`` (never synced as an OANDA trade) or rows
    already missing realized P/L that match a cancel/reject event on ``broker_lot_id``.
    """
    from brokerai.trading.broker.cancelled_orders import find_order_cancellation

    async with session_scope() as session:
        stmt = (
            select(BrokerLotRow)
            .where(
                BrokerLotRow.exchange_id == exchange_id,
                BrokerLotRow.state != "cancelled",
                BrokerLotRow.broker_lot_id != "",
            )
            .limit(500)
        )
        rows = (await session.execute(stmt)).scalars().all()
        candidates = [dict(row.doc) for row in rows]
    marked = 0

    for lot in candidates:
        if lot.get("raw_broker"):
            continue
        broker_id = _local_broker_id(lot)
        if not broker_id:
            continue
        lot_account = str(lot.get("account_id") or account_id or "")
        cancellation = await find_order_cancellation(
            exchange_id,
            broker_id,
            account_id=lot_account or account_id,
        )
        if cancellation is None:
            continue
        await lots_repo.cancel_lot(
            str(lot.get("id")),
            reason=str(cancellation.get("reason") or "order_cancelled"),
            cancelled_at=cancellation.get("cancelled_at"),
        )
        marked += 1

    return marked


def reconcile_sync_drift(
    local_lots: list[dict[str, Any]],
    broker_lots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare local ``broker_lots`` cache against live broker open lots."""
    unmatched_local = list(local_lots)
    unmatched_broker = list(broker_lots)
    matched: list[dict[str, Any]] = []

    broker_by_id = {str(t.get("broker_lot_id") or t.get("id", "")): t for t in broker_lots}
    for local in list(unmatched_local):
        lot_id = str(local.get("broker_lot_id") or "")
        if not lot_id:
            continue
        broker = broker_by_id.get(lot_id)
        if broker is None:
            continue
        matched.append(
            {
                "local_lot_id": local.get("id"),
                "broker_lot_id": lot_id,
                "pair": local.get("pair"),
                "direction": local.get("direction"),
                "match_type": "broker_lot_id",
            }
        )
        unmatched_local.remove(local)
        broker_key = str(broker.get("broker_lot_id") or broker.get("id", ""))
        unmatched_broker = [
            b
            for b in unmatched_broker
            if str(b.get("broker_lot_id") or b.get("id", "")) != broker_key
        ]

    def _key(trade: dict[str, Any]) -> tuple[str, str]:
        pair = str(trade.get("pair", "")).replace("_", "/").upper()
        direction = str(trade.get("direction", "")).lower()
        return pair, direction

    for local in list(unmatched_local):
        key = _key(local)
        broker_match = next((b for b in unmatched_broker if _key(b) == key), None)
        if broker_match is None:
            continue
        matched.append(
            {
                "local_lot_id": local.get("id"),
                "broker_lot_id": broker_match.get("broker_lot_id") or broker_match.get("id"),
                "pair": local.get("pair"),
                "direction": local.get("direction"),
                "match_type": "pair_direction",
            }
        )
        unmatched_local.remove(local)
        unmatched_broker.remove(broker_match)

    local_count = len(local_lots)
    broker_count = len(broker_lots)
    status = "matched" if local_count == broker_count and not unmatched_local and not unmatched_broker else "mismatch"

    lot_badges = {str(m["local_lot_id"]): "matched" for m in matched}
    for lot in unmatched_local:
        lot_badges[str(lot.get("id", ""))] = "local_only"

    broker_by_id = {str(t.get("broker_lot_id") or t.get("id", "")): t for t in broker_lots}
    lot_market: dict[str, dict[str, Any]] = {}
    for match in matched:
        local_id = str(match.get("local_lot_id", ""))
        broker_id = str(match.get("broker_lot_id", ""))
        broker = broker_by_id.get(broker_id)
        if not local_id or broker is None:
            continue
        lot_market[local_id] = {
            "current_price": broker.get("current_price"),
            "unrealized_pl": broker.get("unrealized_pl"),
        }

    return {
        "local_open_count": local_count,
        "broker_open_count": broker_count,
        "ledger_open_count": local_count,
        "status": status,
        "matched": matched,
        "lot_badges": lot_badges,
        "ledger_badges": lot_badges,
        "lot_market": lot_market,
        "ledger_market": lot_market,
        "unmatched_local": unmatched_local,
        "unmatched_ledger": unmatched_local,
        "unmatched_broker": unmatched_broker,
        "broker_lots": broker_lots,
    }


def unconfigured_reconciliation() -> dict[str, Any]:
    return {
        "configured": False,
        "local_open_count": 0,
        "broker_open_count": 0,
        "ledger_open_count": 0,
        "status": "unconfigured",
        "matched": [],
        "lot_badges": {},
        "ledger_badges": {},
        "lot_market": {},
        "ledger_market": {},
        "unmatched_local": [],
        "unmatched_ledger": [],
        "unmatched_broker": [],
        "broker_lots": [],
    }
