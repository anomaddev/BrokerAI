from __future__ import annotations

from datetime import datetime, timezone

from brokerai.trading.broker.child_orders import (
    apply_child_orders_from_events,
    reconcile_child_order,
)
from brokerai.trading.broker.close_reason import infer_close_reason
from brokerai.trading.broker.models import BrokerEvent, ChildOrder, PositionLot


def _closed_lot(**kwargs) -> PositionLot:
    base = dict(
        exchange_id="oanda",
        account_id="acct",
        broker_lot_id="562",
        asset_class="forex",
        state="closed",
        instrument="EUR_JPY",
        symbol="EUR_JPY",
        direction="long",
        initial_qty=1000,
        current_qty=0,
        entry_price=114.0,
        closing_event_ids=["520"],
    )
    base.update(kwargs)
    return PositionLot(**base)


def test_apply_child_orders_from_events_marks_sl_filled_from_closing_txn():
    lot = _closed_lot(
        stop_loss=ChildOrder(
            broker_order_id="519",
            order_type="STOP_LOSS",
            state="PENDING",
            price=114.46,
            filling_event_id="520",
        ),
    )
    events = [
        BrokerEvent(
            exchange_id="oanda",
            account_id="acct",
            broker_event_id="520",
            event_type="STOP_LOSS_ORDER",
            time=datetime(2026, 7, 2, 20, 30, tzinfo=timezone.utc),
            broker_lot_id="562",
            broker_order_id="519",
            price=114.46,
        ),
    ]
    updated = apply_child_orders_from_events(lot, events)
    assert updated.stop_loss is not None
    assert updated.stop_loss.state == "FILLED"
    assert updated.stop_loss.filling_event_id == "520"


def test_reconcile_child_order_prefers_event_filled_over_snapshot_pending():
    snapshot = ChildOrder(
        broker_order_id="519",
        order_type="STOP_LOSS",
        state="PENDING",
        price=114.46,
    )
    derived = ChildOrder(
        broker_order_id="519",
        order_type="STOP_LOSS",
        state="FILLED",
        price=114.46,
        filling_event_id="520",
    )
    merged = reconcile_child_order(snapshot, derived, slot="stop_loss", broker_lot_id="562")
    assert merged is not None
    assert merged.state == "FILLED"
    assert merged.filling_event_id == "520"


def test_infer_close_reason_from_closing_stop_loss_event_when_child_cancelled():
    lot = _closed_lot(
        closing_event_ids=["520"],
        stop_loss=ChildOrder(
            broker_order_id="519",
            order_type="STOP_LOSS",
            state="CANCELLED",
            price=114.46,
            cancelling_event_id="518",
        ),
    )
    events = [
        BrokerEvent(
            exchange_id="oanda",
            account_id="acct",
            broker_event_id="520",
            event_type="STOP_LOSS_ORDER",
            time=datetime(2026, 7, 2, 20, 30, tzinfo=timezone.utc),
            broker_lot_id="562",
            broker_order_id="519",
            price=114.46,
        ),
    ]
    assert infer_close_reason(lot, events) == "stop_loss"


def test_order_cancel_marks_child_cancelled():
    lot = _closed_lot(
        state="open",
        closing_event_ids=[],
        stop_loss=ChildOrder(
            broker_order_id="519",
            order_type="STOP_LOSS",
            state="PENDING",
            price=114.46,
        ),
    )
    events = [
        BrokerEvent(
            exchange_id="oanda",
            account_id="acct",
            broker_event_id="521",
            event_type="ORDER_CANCEL",
            time=datetime(2026, 7, 2, 20, 31, tzinfo=timezone.utc),
            broker_lot_id="562",
            broker_order_id="519",
        ),
    ]
    updated = apply_child_orders_from_events(lot, events)
    assert updated.stop_loss is not None
    assert updated.stop_loss.state == "CANCELLED"
    assert updated.stop_loss.cancelling_event_id == "521"
