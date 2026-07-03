from __future__ import annotations

from typing import Any

from brokerai.trading.broker.models import BrokerEvent, ChildOrder, PositionLot


def infer_close_reason(lot: PositionLot, events: list[BrokerEvent] | None = None) -> str:
    """Infer ``close_reason`` from child order states and broker events.

    Priority:
    1. SL/TP order filled
    2. Partial close (multiple closing events)
    3. ORDER_FILL with MARKET_ORDER reason
    4. Already set close_reason (strategy_exit, manual_close)
    5. broker_closed (fallback)
    """
    if lot.state != "closed":
        return lot.close_reason or ""

    if lot.close_reason in ("strategy_exit", "manual_close"):
        return lot.close_reason

    if lot.stop_loss and lot.stop_loss.state.upper() == "FILLED":
        return "stop_loss"
    if lot.take_profit and lot.take_profit.state.upper() == "FILLED":
        return "take_profit"

    if len(lot.closing_event_ids) > 1:
        return "partial_close"

    if events:
        closing_set = set(lot.closing_event_ids)
        for event in events:
            if event.broker_event_id in closing_set or event.broker_lot_id == lot.broker_lot_id:
                event_type = event.event_type.upper()
                reason = (event.reason or "").upper()
                if event_type == "ORDER_FILL" and reason in ("MARKET_ORDER", "CLIENT"):
                    return "manual_close"

    return lot.close_reason or "broker_closed"


def enrich_lot_from_events(lot: PositionLot, events: list[BrokerEvent]) -> PositionLot:
    """Attach entry batch and close reason from related events."""
    lot_events = [
        e
        for e in events
        if e.broker_lot_id == lot.broker_lot_id
        or e.broker_event_id in lot.closing_event_ids
    ]
    if lot_events and not lot.entry_batch_id:
        for event in lot_events:
            if event.batch_id:
                lot.entry_batch_id = event.batch_id
                break

    if lot.state == "closed" and not lot.close_reason:
        lot.close_reason = infer_close_reason(lot, lot_events)

    if lot_events:
        lot.last_event_id = lot_events[-1].broker_event_id

    return lot


def close_details_from_broker_events(
    events: list[BrokerEvent | dict[str, Any]],
    *,
    closing_event_ids: list[str] | None = None,
    broker_lot_id: str | None = None,
) -> dict[str, Any]:
    """Extract exit price / realized P/L from synced broker events.

    Prefers events listed in ``closing_event_ids``. When those are absent,
    uses the latest ``ORDER_FILL`` for *broker_lot_id*. Partial closes sum
    realized P/L across matching fill events.
    """
    closing_ids = {str(x) for x in (closing_event_ids or []) if x}
    fill_types = {"ORDER_FILL", "MARKET_ORDER", "TAKE_PROFIT_ORDER", "STOP_LOSS_ORDER"}

    selected: list[BrokerEvent | dict[str, Any]] = []
    for event in events:
        if isinstance(event, BrokerEvent):
            event_id = event.broker_event_id
            event_type = event.event_type.upper()
            lot_id = event.broker_lot_id
        else:
            event_id = str(event.get("broker_event_id", ""))
            event_type = str(event.get("event_type", "")).upper()
            lot_id = event.get("broker_lot_id")

        if closing_ids and event_id in closing_ids:
            selected.append(event)
            continue
        if not closing_ids and broker_lot_id and lot_id == broker_lot_id and event_type in fill_types:
            selected.append(event)

    if not selected:
        return {}

    exit_price: float | None = None
    closed_at = None
    total_pl = 0.0
    found_pl = False

    for event in selected:
        if isinstance(event, BrokerEvent):
            price = event.price
            pl = event.pl
            when = event.time
            event_type = event.event_type.upper()
        else:
            price = event.get("price")
            pl = event.get("pl")
            when = event.get("time")
            event_type = str(event.get("event_type", "")).upper()

        if event_type == "ORDER_FILL" or pl is not None:
            if price is not None:
                exit_price = float(price)
            if pl is not None:
                total_pl += float(pl)
                found_pl = True
            if when is not None and closed_at is None:
                closed_at = when

    result: dict[str, Any] = {}
    if exit_price is not None:
        result["exit_price"] = exit_price
    if found_pl:
        result["realized_pl"] = total_pl
    if closed_at is not None:
        result["closed_at"] = closed_at
    return result
