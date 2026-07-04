from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from brokerai.trading.broker.models import BrokerEvent, ChildOrder, PositionLot

logger = logging.getLogger(__name__)

ChildOrderSlot = Literal["stop_loss", "take_profit"]

_SL_TYPES = frozenset({"STOP_LOSS_ORDER", "STOP_LOSS"})
_TP_TYPES = frozenset({"TAKE_PROFIT_ORDER", "TAKE_PROFIT"})
_CREATION_TYPES = _SL_TYPES | _TP_TYPES
_FILL_EVENT_TYPES = frozenset({"ORDER_FILL", "STOP_LOSS_ORDER", "TAKE_PROFIT_ORDER"})
_TERMINAL_STATES = frozenset({"FILLED", "CANCELLED"})


def _slot_for_order_type(order_type: str) -> ChildOrderSlot | None:
    upper = order_type.upper()
    if upper in _SL_TYPES or ("STOP" in upper and "LOSS" in upper):
        return "stop_loss"
    if upper in _TP_TYPES or ("TAKE" in upper and "PROFIT" in upper):
        return "take_profit"
    return None


def _slot_for_event_type(event_type: str) -> ChildOrderSlot | None:
    return _slot_for_order_type(event_type)


def _state_rank(state: str) -> int:
    upper = state.upper()
    if upper in _TERMINAL_STATES:
        return 2
    if upper == "PENDING":
        return 1
    return 0


def _event_sort_key(event: BrokerEvent) -> tuple[datetime, str]:
    when = event.time
    if when is None:
        when = datetime.min.replace(tzinfo=timezone.utc)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (when, event.broker_event_id)


def _related_lot_events(lot: PositionLot, events: list[BrokerEvent]) -> list[BrokerEvent]:
    closing_ids = set(lot.closing_event_ids)
    child_order_ids: set[str] = set()
    for child in (lot.stop_loss, lot.take_profit):
        if child and child.broker_order_id:
            child_order_ids.add(child.broker_order_id)

    selected: list[BrokerEvent] = []
    for event in events:
        if event.broker_lot_id == lot.broker_lot_id:
            selected.append(event)
            continue
        if event.broker_event_id in closing_ids:
            selected.append(event)
            continue
        if event.broker_order_id and event.broker_order_id in child_order_ids:
            selected.append(event)
    return selected


def _derive_child_orders_from_events(
    lot: PositionLot,
    events: list[BrokerEvent],
) -> dict[ChildOrderSlot, ChildOrder]:
    """Build event-derived SL/TP state from chronologically ordered transactions."""
    lot_events = sorted(_related_lot_events(lot, events), key=_event_sort_key)
    closing_ids = set(lot.closing_event_ids)
    by_order_id: dict[str, ChildOrder] = {}
    derived: dict[ChildOrderSlot, ChildOrder] = {}

    for slot_name, child in (("stop_loss", lot.stop_loss), ("take_profit", lot.take_profit)):
        if child is None or not child.broker_order_id:
            continue
        seeded = ChildOrder.from_dict(child.to_dict()) or child
        by_order_id[child.broker_order_id] = seeded
        derived[slot_name] = seeded

    def _ensure_child(
        *,
        slot: ChildOrderSlot,
        order_id: str,
        order_type: str,
        price: float | None,
        when: datetime | None,
    ) -> ChildOrder:
        existing = by_order_id.get(order_id)
        if existing is None:
            existing = ChildOrder(
                broker_order_id=order_id,
                order_type=order_type,
                state="PENDING",
                price=price,
                trade_id=lot.broker_lot_id,
                create_time=when,
            )
            by_order_id[order_id] = existing
            derived[slot] = existing
        elif price is not None and existing.price is None:
            existing.price = price
        return existing

    for event in lot_events:
        event_type = event.event_type.upper()
        order_id = str(event.broker_order_id or "").strip()
        slot = _slot_for_event_type(event_type)

        if slot and event_type in _CREATION_TYPES:
            oid = order_id or event.broker_event_id
            child = _ensure_child(
                slot=slot,
                order_id=oid,
                order_type=event_type,
                price=event.price,
                when=event.time,
            )
            if event.broker_event_id in closing_ids:
                child.state = "FILLED"
                child.filled_time = event.time
                child.filling_event_id = event.broker_event_id
            continue

        if event_type == "ORDER_FILL" and order_id and order_id in by_order_id:
            child = by_order_id[order_id]
            child.state = "FILLED"
            child.filled_time = event.time
            child.filling_event_id = event.broker_event_id
            continue

        if event_type == "ORDER_CANCEL" and order_id and order_id in by_order_id:
            child = by_order_id[order_id]
            child.state = "CANCELLED"
            child.cancelling_event_id = event.broker_event_id
            continue

        if event.broker_event_id in closing_ids and event_type in _FILL_EVENT_TYPES:
            slot_from_type = _slot_for_event_type(event_type)
            if slot_from_type and order_id:
                child = _ensure_child(
                    slot=slot_from_type,
                    order_id=order_id,
                    order_type=event_type,
                    price=event.price,
                    when=event.time,
                )
                child.state = "FILLED"
                child.filled_time = event.time
                child.filling_event_id = event.broker_event_id

    for child in (lot.stop_loss, lot.take_profit):
        if child is None or not child.broker_order_id:
            continue
        slot = _slot_for_order_type(child.order_type)
        if slot is None:
            continue
        tracked = by_order_id.get(child.broker_order_id)
        if tracked is None:
            derived.setdefault(slot, ChildOrder.from_dict(child.to_dict()) or child)
            by_order_id[child.broker_order_id] = derived[slot]
        if child.filling_event_id:
            fill_event = next(
                (e for e in lot_events if e.broker_event_id == child.filling_event_id),
                None,
            )
            if fill_event and tracked:
                tracked.state = "FILLED"
                tracked.filled_time = fill_event.time
                tracked.filling_event_id = child.filling_event_id
        if child.cancelling_event_id:
            cancel_event = next(
                (e for e in lot_events if e.broker_event_id == child.cancelling_event_id),
                None,
            )
            if cancel_event and tracked:
                tracked.state = "CANCELLED"
                tracked.cancelling_event_id = child.cancelling_event_id

    return derived


def reconcile_child_order(
    snapshot: ChildOrder | None,
    derived: ChildOrder | None,
    *,
    slot: ChildOrderSlot,
    broker_lot_id: str,
) -> ChildOrder | None:
    """Merge broker trade snapshot with event-derived child order state."""
    if snapshot is None:
        return derived
    if derived is None:
        return snapshot

    snap_rank = _state_rank(snapshot.state)
    derived_rank = _state_rank(derived.state)

    if snap_rank > derived_rank:
        if snapshot.state.upper() != derived.state.upper():
            logger.warning(
                "Child order drift %s lot=%s order=%s snapshot=%s derived=%s (keeping snapshot)",
                slot,
                broker_lot_id,
                snapshot.broker_order_id,
                snapshot.state,
                derived.state,
            )
        return snapshot

    if derived_rank > snap_rank:
        merged = ChildOrder.from_dict(snapshot.to_dict()) or snapshot
        merged.state = derived.state
        if derived.filled_time:
            merged.filled_time = derived.filled_time
        if derived.filling_event_id:
            merged.filling_event_id = derived.filling_event_id
        if derived.cancelling_event_id:
            merged.cancelling_event_id = derived.cancelling_event_id
        if derived.price is not None and merged.price is None:
            merged.price = derived.price
        logger.info(
            "Child order event transition %s lot=%s order=%s %s -> %s",
            slot,
            broker_lot_id,
            merged.broker_order_id,
            snapshot.state,
            merged.state,
        )
        return merged

    if snapshot.state.upper() != derived.state.upper():
        logger.warning(
            "Child order state tie %s lot=%s order=%s snapshot=%s derived=%s (keeping snapshot)",
            slot,
            broker_lot_id,
            snapshot.broker_order_id,
            snapshot.state,
            derived.state,
        )
    return snapshot


def validate_child_order_linkage(lot: PositionLot) -> None:
    """Log linkage mismatches between child orders and closing transaction IDs."""
    if lot.state != "closed":
        return
    closing_ids = set(lot.closing_event_ids)
    for slot, child in (("stop_loss", lot.stop_loss), ("take_profit", lot.take_profit)):
        if child is None:
            continue
        if child.filling_event_id and child.state.upper() == "FILLED":
            if closing_ids and child.filling_event_id not in closing_ids:
                logger.warning(
                    "Child order fill txn not in closing_event_ids %s lot=%s order=%s fill_txn=%s",
                    slot,
                    lot.broker_lot_id,
                    child.broker_order_id,
                    child.filling_event_id,
                )


def apply_child_orders_from_events(lot: PositionLot, events: list[BrokerEvent]) -> PositionLot:
    """Apply event-driven SL/TP transitions and reconcile against trade snapshot."""
    derived = _derive_child_orders_from_events(lot, events)
    lot.stop_loss = reconcile_child_order(
        lot.stop_loss,
        derived.get("stop_loss"),
        slot="stop_loss",
        broker_lot_id=lot.broker_lot_id,
    )
    lot.take_profit = reconcile_child_order(
        lot.take_profit,
        derived.get("take_profit"),
        slot="take_profit",
        broker_lot_id=lot.broker_lot_id,
    )
    validate_child_order_linkage(lot)
    return lot


def merge_child_order_patch(lot: PositionLot, child: ChildOrder) -> PositionLot:
    """Merge a standalone child-order patch from /changes order arrays."""
    slot = _slot_for_order_type(child.order_type)
    if slot == "stop_loss":
        lot.stop_loss = reconcile_child_order(
            lot.stop_loss,
            child,
            slot="stop_loss",
            broker_lot_id=lot.broker_lot_id,
        )
        if lot.stop_loss and lot.stop_loss.price is not None:
            lot.stop_loss_price = lot.stop_loss.price
    elif slot == "take_profit":
        lot.take_profit = reconcile_child_order(
            lot.take_profit,
            child,
            slot="take_profit",
            broker_lot_id=lot.broker_lot_id,
        )
        if lot.take_profit and lot.take_profit.price is not None:
            lot.take_profit_price = lot.take_profit.price
    return lot
