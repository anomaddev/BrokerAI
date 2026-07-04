from __future__ import annotations

from datetime import datetime, timezone

import pytest

from brokerai.trading.broker.event_retention import (
    classify_event_retention,
    collect_protected_event_ids,
)
from brokerai.trading.broker.models import BrokerEvent


def _event(
    *,
    event_id: str = "1",
    event_type: str = "ORDER_FILL",
    broker_lot_id: str | None = "565",
    broker_order_id: str | None = None,
) -> BrokerEvent:
    return BrokerEvent(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_event_id=event_id,
        event_type=event_type,
        time=datetime(2026, 7, 2, 20, 27, 24, tzinfo=timezone.utc),
        broker_lot_id=broker_lot_id,
        broker_order_id=broker_order_id,
    )


def test_trade_linked_event_has_no_retention_expiry():
    expires = classify_event_retention(_event(event_type="ORDER_FILL"))
    assert expires is None


def test_low_value_event_gets_retention_expiry():
    expires = classify_event_retention(
        _event(event_type="MARGIN_CALL", broker_lot_id=None),
        retention_days=90,
    )
    assert expires is not None
    assert expires > datetime.now(timezone.utc)


def test_protected_event_ids_skip_ttl():
    expires = classify_event_retention(
        _event(event_type="MARGIN_CALL", broker_lot_id=None, event_id="99"),
        protected_event_ids=frozenset({"99"}),
    )
    assert expires is None


def test_collect_protected_event_ids_from_open_lot():
    lot = {
        "state": "open",
        "last_event_id": "10",
        "closing_event_ids": ["11"],
        "stop_loss": {"filling_event_id": "12", "cancelling_event_id": "13"},
    }
    protected = collect_protected_event_ids([lot])
    assert protected == frozenset({"10", "11", "12", "13"})


def test_unclassified_event_without_linkage_is_kept():
    expires = classify_event_retention(
        _event(event_type="UNKNOWN_ADMIN", broker_lot_id=None),
    )
    assert expires is None
