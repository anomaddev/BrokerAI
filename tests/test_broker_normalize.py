from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brokerai.integrations.oanda import normalize_oanda_transaction
from brokerai.trading.broker.adapters.oanda import event_from_oanda_transaction, lot_from_oanda_trade
from brokerai.trading.broker.close_reason import close_details_from_broker_events, infer_close_reason
from brokerai.trading.broker.models import ChildOrder, PositionLot

FIXTURES = Path(__file__).resolve().parents[1] / ".response_data" / "oanda"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_lot_from_open_trade_fixture():
    payload = _load_json("trades/open_trades.json")
    raw_trade = payload["trades"][0]
    lot = lot_from_oanda_trade(
        {
            "id": raw_trade["id"],
            "instrument": raw_trade["instrument"],
            "direction": "short",
            "initial_units": abs(float(raw_trade["initialUnits"])),
            "current_units": abs(float(raw_trade["currentUnits"])),
            "entry_price": float(raw_trade["price"]),
            "unrealized_pl": float(raw_trade["unrealizedPL"]),
            "open_time": raw_trade["openTime"],
            "state": raw_trade["state"],
            "stop_loss": {
                "broker_order_id": raw_trade["stopLossOrder"]["id"],
                "order_type": raw_trade["stopLossOrder"]["type"],
                "state": raw_trade["stopLossOrder"]["state"],
                "price": float(raw_trade["stopLossOrder"]["price"]),
            },
        },
        exchange_id="oanda",
        account_id="101-001-test",
    )
    assert lot.broker_lot_id == raw_trade["id"]
    assert lot.state == "open"
    assert lot.stop_loss is not None
    assert lot.stop_loss.state == "PENDING"
    assert lot.pair == "EUR/JPY"


def test_event_from_transaction_fixture():
    raw = _load_json("transactions/transaction_563.json")
    normalized = normalize_oanda_transaction(raw)
    assert normalized is not None
    event = event_from_oanda_transaction(
        normalized,
        exchange_id="oanda",
        account_id="101-001-test",
    )
    assert event.event_type == "STOP_LOSS_ORDER"
    assert event.broker_lot_id == "562"
    assert event.batch_id == "561"


def test_infer_close_reason_stop_loss():
    lot = PositionLot(
        exchange_id="oanda",
        account_id="a",
        broker_lot_id="1",
        asset_class="forex",
        state="closed",
        instrument="EUR_USD",
        symbol="EUR_USD",
        direction="long",
        initial_qty=1000,
        current_qty=0,
        entry_price=1.1,
        stop_loss=ChildOrder(
            broker_order_id="2",
            order_type="STOP_LOSS",
            state="FILLED",
            price=1.09,
        ),
    )
    assert infer_close_reason(lot) == "stop_loss"


def test_infer_close_reason_partial_close():
    lot = PositionLot(
        exchange_id="oanda",
        account_id="a",
        broker_lot_id="434",
        asset_class="forex",
        state="closed",
        instrument="EUR_JPY",
        symbol="EUR_JPY",
        direction="long",
        initial_qty=1000,
        current_qty=0,
        entry_price=180.0,
        closing_event_ids=["518", "523"],
    )
    assert infer_close_reason(lot) == "partial_close"


def test_close_details_from_broker_events_closing_txn_ids():
    closed_at = datetime(2026, 6, 30, 14, 30, tzinfo=timezone.utc)
    details = close_details_from_broker_events(
        [
            {
                "broker_event_id": "523",
                "broker_lot_id": "434",
                "event_type": "ORDER_FILL",
                "price": 184.5,
                "pl": 12.3,
                "time": closed_at,
            }
        ],
        closing_event_ids=["523"],
        broker_lot_id="434",
    )
    assert details["exit_price"] == 184.5
    assert details["realized_pl"] == 12.3
    assert details["closed_at"] == closed_at
