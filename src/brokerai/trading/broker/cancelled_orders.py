"""Detect OANDA orders that were cancelled or rejected before a trade opened."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from brokerai.db.client import get_db

_ORDER_EVENT_TYPES = frozenset({"MARKET_ORDER", "LIMIT_ORDER", "STOP_ORDER"})
_REJECT_EVENT_TYPES = frozenset({"MARKET_ORDER_REJECT", "LIMIT_ORDER_REJECT", "STOP_ORDER_REJECT"})


async def find_order_cancellation(
    exchange_id: str,
    order_id: str,
    *,
    account_id: str | None = None,
) -> dict[str, Any] | None:
    """Return cancellation metadata when ``order_id`` is a broker order txn, not a trade.

    Checks ``ORDER_CANCEL`` rows referencing the order, ``MARKET_ORDER_REJECT`` on the
    same id, or an ``ORDER_CANCEL`` in the same batch as a submitted order txn.

    Edge cases:
    - Empty ``account_id`` on the lot falls back to any account on the exchange.
    - Returns ``None`` when the id is a real trade with no cancel/reject events.
    """
    order_id = str(order_id or "").strip()
    if not order_id:
        return None

    handle = await get_db()
    collection = handle.db.broker_events

    async def _find_one(query: dict[str, Any]) -> dict[str, Any] | None:
        scoped = {**query, "exchange_id": exchange_id}
        if account_id:
            scoped["account_id"] = account_id
            doc = await collection.find_one(scoped, {"_id": 0})
            if doc is not None:
                return doc
        return await collection.find_one(
            {**query, "exchange_id": exchange_id},
            {"_id": 0},
        )

    cancel = await _find_one(
        {
            "event_type": "ORDER_CANCEL",
            "broker_order_id": order_id,
        }
    )
    if cancel is not None:
        return _cancel_payload(cancel, source="ORDER_CANCEL")

    reject = await _find_one(
        {
            "broker_event_id": order_id,
            "event_type": {"$in": list(_REJECT_EVENT_TYPES)},
        }
    )
    if reject is not None:
        reason = str(reject.get("reason") or reject.get("raw", {}).get("rejectReason") or "ORDER_REJECTED")
        return {
            "reason": reason,
            "cancelled_at": reject.get("time"),
            "event_type": str(reject.get("event_type") or "ORDER_REJECTED"),
            "source": "ORDER_REJECT",
        }

    order = await _find_one(
        {
            "broker_event_id": order_id,
            "event_type": {"$in": list(_ORDER_EVENT_TYPES)},
        }
    )
    if order is None:
        return None

    batch_id = str(order.get("batch_id") or "")
    if batch_id:
        batch_cancel = await _find_one(
            {
                "batch_id": batch_id,
                "event_type": "ORDER_CANCEL",
            }
        )
        if batch_cancel is not None:
            return _cancel_payload(batch_cancel, source="ORDER_CANCEL")

    return None


def _cancel_payload(event: dict[str, Any], *, source: str) -> dict[str, Any]:
    reason = str(event.get("reason") or event.get("raw", {}).get("reason") or "ORDER_CANCELLED")
    cancelled_at = event.get("time")
    if isinstance(cancelled_at, datetime):
        pass
    elif isinstance(cancelled_at, str) and cancelled_at.strip():
        try:
            cancelled_at = datetime.fromisoformat(cancelled_at.replace("Z", "+00:00"))
        except ValueError:
            cancelled_at = None
    else:
        cancelled_at = None
    return {
        "reason": reason,
        "cancelled_at": cancelled_at,
        "event_type": str(event.get("event_type") or "ORDER_CANCEL"),
        "source": source,
    }
