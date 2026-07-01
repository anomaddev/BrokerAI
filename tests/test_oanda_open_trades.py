from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from brokerai.integrations.oanda import (
    _normalize_oanda_closed_trade,
    _normalize_oanda_open_trade,
    _pricing_mid_price,
    attach_current_prices_to_broker_trades,
    extract_broker_trade_id,
    get_broker_open_trades_snapshot,
    parse_oanda_close_response,
)


def test_normalize_oanda_closed_trade_extracts_close_fields():
    trade = _normalize_oanda_closed_trade(
        {
            "id": "88",
            "instrument": "EUR_USD",
            "initialUnits": "-1000",
            "state": "CLOSED",
            "price": "1.10000",
            "averageClosePrice": "1.10500",
            "realizedPL": "-5.00",
            "openTime": "2026-06-30T12:00:00.000000000Z",
            "closeTime": "2026-06-30T14:30:00.000000000Z",
        }
    )
    assert trade is not None
    assert trade["direction"] == "short"
    assert trade["exit_price"] == 1.105
    assert trade["realized_pl"] == -5.0
    assert trade["closed_at"] is not None


def test_parse_oanda_close_response_from_order_fill():
    parsed = parse_oanda_close_response(
        {
            "orderFillTransaction": {
                "price": "1.10500",
                "pl": "12.34",
                "time": "2026-06-30T14:30:00.000000000Z",
                "tradeClosed": {
                    "tradeID": "99",
                    "realizedPL": "12.34",
                },
            }
        }
    )
    assert parsed["exit_price"] == 1.105
    assert parsed["realized_pl"] == 12.34
    assert parsed["broker_trade_id"] == "99"
    assert parsed["closed_at"] is not None


def test_parse_oanda_close_response_sums_trades_closed_pl():
    parsed = parse_oanda_close_response(
        {
            "orderFillTransaction": {
                "price": "1.10500",
                "tradesClosed": [
                    {"realizedPL": "2.00", "tradeID": "1"},
                    {"realizedPL": "-0.50", "tradeID": "1"},
                ],
            }
        }
    )
    assert parsed["realized_pl"] == 1.5


def test_normalize_oanda_open_trade_rejects_zero_units():
    assert _normalize_oanda_open_trade(
        {
            "id": "99",
            "instrument": "EUR_USD",
            "currentUnits": "0",
            "state": "OPEN",
            "price": "1.1000",
        }
    ) is None


def test_normalize_oanda_open_trade_rejects_non_open_state():
    assert _normalize_oanda_open_trade(
        {
            "id": "99",
            "instrument": "EUR_USD",
            "currentUnits": "1000",
            "state": "CLOSED",
            "price": "1.1000",
        }
    ) is None


def test_normalize_oanda_open_trade_accepts_open_trade():
    trade = _normalize_oanda_open_trade(
        {
            "id": "99",
            "instrument": "EUR_USD",
            "currentUnits": "1000",
            "state": "OPEN",
            "price": "1.1000",
            "unrealizedPL": "12.34",
        }
    )
    assert trade is not None
    assert trade["id"] == "99"
    assert trade["direction"] == "long"
    assert trade["unrealized_pl"] == 12.34
    assert trade["current_price"] is None


def test_pricing_mid_price_uses_bid_ask_average():
    assert _pricing_mid_price(
        {
            "instrument": "EUR_USD",
            "bids": [{"price": "1.10000"}],
            "asks": [{"price": "1.10020"}],
        }
    ) == pytest.approx(1.10010)


def test_attach_current_prices_to_broker_trades():
    trades = [
        {"instrument": "EUR_USD", "current_price": None},
        {"instrument": "GBP_USD", "current_price": None},
    ]
    attach_current_prices_to_broker_trades(trades, {"EUR_USD": 1.23456})
    assert trades[0]["current_price"] == 1.23456
    assert trades[1]["current_price"] is None


def test_extract_broker_trade_id_prefers_trade_opened():
    response = {
        "orderFillTransaction": {
            "id": "tx-1",
            "tradeOpened": {"tradeID": "trade-99"},
        }
    }
    assert extract_broker_trade_id(response) == "trade-99"


@pytest.mark.asyncio
async def test_broker_snapshot_returns_empty_when_summary_count_zero():
    with patch(
        "brokerai.integrations.oanda.get_account_summary",
        new=AsyncMock(return_value={"open_trade_count": 0}),
    ), patch(
        "brokerai.integrations.oanda.list_open_trades",
        new=AsyncMock(return_value=[{"id": "ghost"}]),
    ) as list_mock, patch(
        "brokerai.integrations.oanda.fetch_account_pricing",
        new=AsyncMock(),
    ) as pricing_mock:
        snapshot = await get_broker_open_trades_snapshot("token", "practice", "acct")

    assert snapshot["open_trade_count"] == 0
    assert snapshot["trades"] == []
    list_mock.assert_not_awaited()
    pricing_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_broker_snapshot_attaches_current_prices():
    trades = [{"id": "1", "instrument": "EUR_USD", "current_price": None}]
    with patch(
        "brokerai.integrations.oanda.get_account_summary",
        new=AsyncMock(return_value={"open_trade_count": 1}),
    ), patch(
        "brokerai.integrations.oanda.list_open_trades",
        new=AsyncMock(return_value=trades),
    ), patch(
        "brokerai.integrations.oanda.fetch_account_pricing",
        new=AsyncMock(return_value={"EUR_USD": 1.11111}),
    ):
        snapshot = await get_broker_open_trades_snapshot("token", "practice", "acct")

    assert snapshot["trades"][0]["current_price"] == 1.11111
