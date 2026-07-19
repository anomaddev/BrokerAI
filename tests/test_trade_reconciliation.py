from __future__ import annotations

from brokerai.trading.trade_reconciliation import reconcile_open_trades, unconfigured_reconciliation


def test_reconcile_matches_by_broker_order_id():
    ledger = [
        {
            "id": "ledger-1",
            "pair": "EUR/USD",
            "direction": "long",
            "broker_order_id": "broker-99",
        }
    ]
    broker = [
        {
            "id": "broker-99",
            "pair": "EUR/USD",
            "direction": "long",
            "units": 1000,
            "current_price": 1.10123,
            "unrealized_pl": 4.5,
        }
    ]
    result = reconcile_open_trades(ledger, broker)
    assert result["status"] == "matched"
    assert result["ledger_open_count"] == 1
    assert result["broker_open_count"] == 1
    assert result["ledger_badges"]["ledger-1"] == "matched"
    assert result["ledger_market"]["ledger-1"] == {
        "current_price": 1.10123,
        "unrealized_pl": 4.5,
    }
    assert result["unmatched_ledger"] == []
    assert result["unmatched_broker"] == []


def test_reconcile_pair_direction_fallback():
    ledger = [
        {
            "id": "ledger-1",
            "pair": "EUR/USD",
            "direction": "long",
            "broker_order_id": None,
        }
    ]
    broker = [
        {
            "id": "broker-1",
            "pair": "EUR/USD",
            "direction": "long",
            "units": 1000,
        }
    ]
    result = reconcile_open_trades(ledger, broker)
    assert result["status"] == "matched"
    assert result["matched"][0]["match_type"] == "pair_direction"


def test_reconcile_detects_mismatch():
    ledger = [{"id": "l1", "pair": "EUR/USD", "direction": "long", "broker_order_id": None}]
    broker = [{"id": "b1", "pair": "GBP/USD", "direction": "short", "units": 500}]
    result = reconcile_open_trades(ledger, broker)
    assert result["status"] == "mismatch"
    assert result["ledger_badges"]["l1"] == "ledger_only"
    assert len(result["unmatched_broker"]) == 1


def test_unconfigured_reconciliation():
    payload = unconfigured_reconciliation()
    assert payload["configured"] is False
    assert payload["status"] == "unconfigured"
    assert payload["ledger_market"] == {}
