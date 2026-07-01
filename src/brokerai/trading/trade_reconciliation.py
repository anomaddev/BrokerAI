from __future__ import annotations

from typing import Any


def _normalize_pair(pair: str) -> str:
    return pair.replace("_", "/").strip().upper()


def _ledger_match_key(trade: dict[str, Any]) -> tuple[str, str]:
    pair = _normalize_pair(str(trade.get("pair", "")))
    direction = str(trade.get("direction", "")).lower()
    return pair, direction


def _broker_match_key(trade: dict[str, Any]) -> tuple[str, str]:
    pair = _normalize_pair(str(trade.get("pair", "")))
    direction = str(trade.get("direction", "")).lower()
    return pair, direction


def reconcile_open_trades(
    ledger_trades: list[dict[str, Any]],
    broker_trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare MongoDB open trades against broker open trades.

    Match priority:
    1. ``broker_order_id`` equals broker trade ``id``
    2. ``(pair, direction)`` fuzzy match (one broker trade per ledger trade)

    Returns reconciliation payload suitable for the trades API.
    """
    unmatched_ledger = list(ledger_trades)
    unmatched_broker = list(broker_trades)
    matched: list[dict[str, Any]] = []

    # Pass 1: broker_order_id exact match
    broker_by_id = {str(t.get("id", "")): t for t in broker_trades if t.get("id")}
    for ledger in list(unmatched_ledger):
        order_id = ledger.get("broker_order_id")
        if not order_id:
            continue
        broker = broker_by_id.get(str(order_id))
        if broker is None:
            continue
        matched.append(
            {
                "ledger_trade_id": ledger.get("id"),
                "broker_trade_id": broker.get("id"),
                "pair": ledger.get("pair"),
                "direction": ledger.get("direction"),
                "match_type": "broker_order_id",
            }
        )
        unmatched_ledger.remove(ledger)
        if broker in unmatched_broker:
            unmatched_broker.remove(broker)

    # Pass 2: (pair, direction) fuzzy match
    for ledger in list(unmatched_ledger):
        key = _ledger_match_key(ledger)
        broker_match = None
        for broker in unmatched_broker:
            if _broker_match_key(broker) == key:
                broker_match = broker
                break
        if broker_match is None:
            continue
        matched.append(
            {
                "ledger_trade_id": ledger.get("id"),
                "broker_trade_id": broker_match.get("id"),
                "pair": ledger.get("pair"),
                "direction": ledger.get("direction"),
                "match_type": "pair_direction",
            }
        )
        unmatched_ledger.remove(ledger)
        unmatched_broker.remove(broker_match)

    mongo_count = len(ledger_trades)
    broker_count = len(broker_trades)
    if mongo_count == broker_count and not unmatched_ledger and not unmatched_broker:
        status = "matched"
    else:
        status = "mismatch"

    ledger_badges = {m["ledger_trade_id"]: "matched" for m in matched}
    for trade in unmatched_ledger:
        ledger_badges[str(trade.get("id", ""))] = "ledger_only"

    broker_by_id = {str(t.get("id", "")): t for t in broker_trades if t.get("id")}
    ledger_market: dict[str, dict[str, Any]] = {}
    for match in matched:
        ledger_id = str(match.get("ledger_trade_id", ""))
        broker_id = str(match.get("broker_trade_id", ""))
        broker = broker_by_id.get(broker_id)
        if not ledger_id or broker is None:
            continue
        ledger_market[ledger_id] = {
            "current_price": broker.get("current_price"),
            "unrealized_pl": broker.get("unrealized_pl"),
        }

    return {
        "mongo_open_count": mongo_count,
        "broker_open_count": broker_count,
        "status": status,
        "matched": matched,
        "ledger_badges": ledger_badges,
        "ledger_market": ledger_market,
        "unmatched_ledger": unmatched_ledger,
        "unmatched_broker": unmatched_broker,
        "broker_trades": broker_trades,
    }


def unconfigured_reconciliation() -> dict[str, Any]:
    """Payload when OANDA is not connected."""
    return {
        "configured": False,
        "mongo_open_count": 0,
        "broker_open_count": 0,
        "status": "unconfigured",
        "matched": [],
        "ledger_badges": {},
        "ledger_market": {},
        "unmatched_ledger": [],
        "unmatched_broker": [],
        "broker_trades": [],
    }
