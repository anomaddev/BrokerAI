from __future__ import annotations

import json
from pathlib import Path

import pytest

from brokerai.trading.oanda_account_state import (
    apply_account_changes,
    apply_account_state,
    detect_transaction_gap,
    summary_changed,
)

_FIXTURES = Path(__file__).resolve().parents[1] / ".response_data" / "oanda"


@pytest.fixture
def account_changes_payload() -> dict:
    return json.loads((_FIXTURES / "account_changes.json").read_text())


@pytest.fixture
def account_details_payload() -> dict:
    return json.loads((_FIXTURES / "account_details.json").read_text())


def test_apply_account_state_sparse_merge(account_changes_payload):
    previous = {"nav": "10050.00", "balance": "10000.00", "unrealized_pl": "50.00"}
    applied = apply_account_state(account_changes_payload["state"], previous_summary=previous)
    assert applied.lot_pl_updates["565"] == 55.0
    assert applied.summary.get("nav") == "10055.00"
    assert "balance" in applied.summary or applied.summary.get("balance") == "10000.00"


def test_apply_account_state_leaves_unmentioned_fields(account_changes_payload):
    previous = {"nav": "10050.00", "margin_used": "500.00"}
    applied = apply_account_state({"trades": account_changes_payload["state"]["trades"]}, previous_summary=previous)
    assert "margin_used" not in applied.summary
    assert applied.lot_pl_updates["565"] == 55.0


def test_apply_account_changes_empty(account_changes_payload):
    applied = apply_account_changes(
        account_changes_payload["changes"],
        exchange_id="oanda",
        account_id="101-001-test",
    )
    assert applied.lots == []
    assert applied.events == []


def test_detect_transaction_gap():
    txns = [{"id": "105"}, {"id": "106"}]
    assert detect_transaction_gap(txns, since_id="100", last_transaction_id="110") is True


def test_detect_transaction_gap_no_gap():
    txns = [{"id": "101"}, {"id": "102"}]
    assert detect_transaction_gap(txns, since_id="100", last_transaction_id="102") is False


def test_apply_account_changes_maps_trades_and_transactions():
    changes = {
        "tradesOpened": [
            {
                "id": "565",
                "instrument": "EUR_JPY",
                "state": "OPEN",
                "initialUnits": "-683",
                "currentUnits": "-683",
                "price": "184.196",
            }
        ],
        "tradesClosed": [
            {
                "id": "553",
                "instrument": "EUR_JPY",
                "state": "CLOSED",
                "initialUnits": "-768",
                "currentUnits": "0",
                "price": "185.000",
                "averageClosePrice": "185.502",
                "realizedPL": "-0.7153",
            }
        ],
        "transactions": [
            {
                "id": "566",
                "type": "ORDER_FILL",
                "time": "2026-07-02T20:27:24.111844157Z",
                "tradeID": "565",
                "orderID": "564",
                "instrument": "EUR_JPY",
                "units": "-683",
                "price": "184.196",
            }
        ],
    }
    applied = apply_account_changes(
        changes,
        exchange_id="oanda",
        account_id="101-001-test",
    )
    assert len(applied.lots) == 2
    assert {lot.broker_lot_id for lot in applied.lots} == {"565", "553"}
    assert len(applied.events) == 1
    assert applied.events[0].broker_lot_id == "565"
    assert applied.counts["trades_opened"] == 1
    assert applied.counts["trades_closed"] == 1
    assert applied.counts["transactions"] == 1


def test_summary_changed_detects_nav_update(account_changes_payload):
    previous = {"nav": "10050.00", "balance": "10000.00"}
    merged = {**previous, "nav": "10055.00"}
    assert summary_changed(merged, previous) is True
    assert summary_changed(previous, previous) is False


def test_apply_account_changes_order_patches_merge_into_lot():
    changes = {
        "tradesOpened": [
            {
                "id": "565",
                "instrument": "EUR_JPY",
                "state": "OPEN",
                "initialUnits": "-683",
                "currentUnits": "-683",
                "price": "184.196",
            }
        ],
        "ordersCreated": [
            {
                "id": "900",
                "type": "STOP_LOSS",
                "tradeID": "565",
                "state": "PENDING",
                "price": "183.500",
                "createTime": "2026-07-02T20:27:23.880732298Z",
            }
        ],
        "transactions": [],
    }
    applied = apply_account_changes(
        changes,
        exchange_id="oanda",
        account_id="101-001-test",
    )
    assert len(applied.child_order_patches) == 1
    open_lot = next(lot for lot in applied.lots if lot.broker_lot_id == "565")
    assert open_lot.stop_loss is not None
    assert open_lot.stop_loss.broker_order_id == "900"
    assert open_lot.stop_loss.state == "PENDING"
    assert applied.counts["orders_created"] == 1

