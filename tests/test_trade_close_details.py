from __future__ import annotations

from brokerai.db.repositories.trades import _execution_reason_from_metadata, serialize_trade
from brokerai.trading.trade_close_details import close_details_from_metadata, resolved_close_fields


def test_resolved_close_fields_uses_metadata_when_top_level_missing():
    doc = {
        "status": "closed",
        "close_metadata": {
            "broker_close": {
                "orderFillTransaction": {
                    "price": "1.10500",
                    "pl": "8.50",
                    "time": "2026-06-30T14:30:00.000000000Z",
                    "tradeClosed": {"tradeID": "99", "realizedPL": "8.50"},
                }
            }
        },
    }
    fields = resolved_close_fields(doc)
    assert fields["exit_price"] == 1.105
    assert fields["realized_pl"] == 8.5


def test_execution_reason_from_metadata_uses_analysis_signal():
    reason = _execution_reason_from_metadata(
        {"analysis": {"signal": "bullish_cross"}, "source": "oanda_sync"}
    )
    assert reason == "bullish_cross"


def test_execution_reason_from_metadata_maps_test_script_source():
    reason = _execution_reason_from_metadata(
        {"source": "scripts/place_random_oanda_trade.py"}
    )
    assert reason == "random_trade"


def test_serialize_trade_includes_execution_reason_for_open_trade():
    doc = {
        "id": "trade-1",
        "status": "open",
        "metadata": {"analysis": {"signal": "bearish_cross"}},
    }
    serialized = serialize_trade(doc)
    assert serialized["execution_reason"] == "bearish_cross"
    assert serialized["reason_display"]["short"] == "Bear cross"
    assert serialized["reason_display"]["category"] == "signal"


def test_serialize_trade_test_script_open_reason():
    doc = {
        "id": "trade-test",
        "status": "open",
        "strategy_id": "test-script",
        "metadata": {"source": "scripts/place_random_oanda_trade.py"},
    }
    serialized = serialize_trade(doc)
    assert serialized["execution_reason"] == "random_trade"
    assert serialized["reason_display"]["short"] == "Random Trade"
    assert serialized["reason_display"]["label"] == "Random Trade"


def test_serialize_trade_reason_display_for_closed_trade():
    doc = {
        "id": "trade-2",
        "status": "closed",
        "close_reason": "manual_close",
    }
    serialized = serialize_trade(doc)
    assert serialized["reason_display"]["short"] == "Manual"
    assert serialized["reason_display"]["category"] == "manual"
    assert serialized["reason_display"]["label"] == "Manual close"


def test_serialize_trade_enriches_closed_trade_from_metadata():
    doc = {
        "id": "trade-1",
        "status": "closed",
        "strategy_id": "s1",
        "strategy_name": "EMA",
        "pair": "EUR/USD",
        "asset_class": "forex",
        "direction": "long",
        "entry_price": 1.1,
        "metadata": {},
        "close_metadata": {
            "broker_close": {
                "orderFillTransaction": {
                    "price": "1.10500",
                    "pl": "-3.25",
                }
            }
        },
    }
    serialized = serialize_trade(doc)
    assert serialized["exit_price"] == 1.105
    assert serialized["realized_pl"] == -3.25


def test_close_details_from_metadata_sums_trades_closed_pl():
    details = close_details_from_metadata(
        {
            "broker_close": {
                "orderFillTransaction": {
                    "tradesClosed": [
                        {"realizedPL": "1.50", "tradeID": "1"},
                        {"realizedPL": "-0.50", "tradeID": "1"},
                    ]
                }
            }
        }
    )
    assert details["realized_pl"] == 1.0
