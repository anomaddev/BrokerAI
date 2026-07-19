"""Detect OANDA orders that were cancelled or rejected before a trade opened."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BrokerEventRow
from brokerai.db.repositories.broker_events import BrokerEventsRepository

_ORDER_EVENT_TYPES = frozenset({"MARKET_ORDER", "LIMIT_ORDER", "STOP_ORDER"})
_REJECT_EVENT_TYPES = frozenset({"MARKET_ORDER_REJECT", "LIMIT_ORDER_REJECT", "STOP_ORDER_REJECT"})


async def _find_event_doc(
    exchange_id: str,
    *,
    account_id: str | None,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    """Match one broker event, preferring *account_id* when provided."""

    async def _query(scoped_account_id: str | None) -> dict[str, Any] | None:
        async with session_scope() as session:
            stmt = select(BrokerEventRow).where(BrokerEventRow.exchange_id == exchange_id)
            if scoped_account_id:
                stmt = stmt.where(BrokerEventRow.account_id == scoped_account_id)
            for key, value in filters.items():
                if key == "event_type_in":
                    stmt = stmt.where(
                        BrokerEventRow.doc["event_type"].as_string().in_(sorted(value))
                    )
                elif key == "event_type":
                    stmt = stmt.where(BrokerEventRow.doc["event_type"].as_string() == value)
                else:
                    stmt = stmt.where(BrokerEventRow.doc[key].as_string() == str(value))
            row = (await session.execute(stmt.limit(1))).scalar_one_or_none()
            return dict(row.doc) if row else None

    if account_id:
        doc = await _query(account_id)
        if doc is not None:
            return doc
    return await _query(None)


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

    events_repo = BrokerEventsRepository()

    if account_id:
        cancels = await events_repo.list_events_by_order_id(
            exchange_id=exchange_id,
            account_id=account_id,
            broker_order_id=order_id,
        )
        cancel = next((doc for doc in cancels if doc.get("event_type") == "ORDER_CANCEL"), None)
        if cancel is not None:
            return _cancel_payload(cancel, source="ORDER_CANCEL")

    cancel = await _find_event_doc(
        exchange_id,
        account_id=account_id,
        filters={
            "event_type": "ORDER_CANCEL",
            "broker_order_id": order_id,
        },
    )
    if cancel is not None:
        return _cancel_payload(cancel, source="ORDER_CANCEL")

    reject = await _find_event_doc(
        exchange_id,
        account_id=account_id,
        filters={
            "broker_event_id": order_id,
            "event_type_in": _REJECT_EVENT_TYPES,
        },
    )
    if reject is not None:
        reason = str(
            reject.get("reason") or reject.get("raw", {}).get("rejectReason") or "ORDER_REJECTED"
        )
        return {
            "reason": reason,
            "cancelled_at": reject.get("time"),
            "event_type": str(reject.get("event_type") or "ORDER_REJECTED"),
            "source": "ORDER_REJECT",
        }

    order = await _find_event_doc(
        exchange_id,
        account_id=account_id,
        filters={
            "broker_event_id": order_id,
            "event_type_in": _ORDER_EVENT_TYPES,
        },
    )
    if order is None:
        return None

    batch_id = str(order.get("batch_id") or "")
    if batch_id:
        batch_cancel = await _find_event_doc(
            exchange_id,
            account_id=account_id,
            filters={
                "batch_id": batch_id,
                "event_type": "ORDER_CANCEL",
            },
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
