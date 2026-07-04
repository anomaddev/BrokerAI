from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.broker.models import BrokerEvent, PositionLot
from brokerai.trading.oanda_bootstrap import OandaBootstrapResult, run_oanda_bootstrap


@pytest.mark.asyncio
async def test_run_oanda_bootstrap_merges_open_and_closed_lots():
    open_trade = {
        "id": "565",
        "instrument": "EUR_JPY",
        "state": "OPEN",
        "initialUnits": "-683",
        "currentUnits": "-683",
        "price": "184.196",
        "openTime": "2026-07-02T20:27:24.111844157Z",
    }
    closed_trade = {
        "id": "553",
        "instrument": "EUR_JPY",
        "state": "CLOSED",
        "initialUnits": "-768",
        "currentUnits": "0",
        "price": "185.000",
        "averageClosePrice": "185.502",
        "realizedPL": "-0.7153",
        "openTime": "2026-07-01T06:00:00.000000000Z",
        "closeTime": "2026-07-01T07:57:16.870490095Z",
    }
    account = {
        "id": "101-001-test",
        "balance": "10000",
        "NAV": "10050",
        "trades": [open_trade],
    }
    txn = {
        "id": "566",
        "type": "ORDER_FILL",
        "time": "2026-07-02T20:27:24.111844157Z",
        "tradeID": "565",
        "orderID": "564",
        "instrument": "EUR_JPY",
        "units": "-683",
        "price": "184.196",
    }

    with patch(
        "brokerai.trading.oanda_bootstrap.get_account_details",
        new=AsyncMock(return_value=(account, "566")),
    ), patch(
        "brokerai.trading.oanda_bootstrap.list_all_trades",
        new=AsyncMock(return_value=([closed_trade], "566")),
    ), patch(
        "brokerai.trading.oanda_bootstrap.list_transactions_idrange",
        new=AsyncMock(return_value=([txn], "566")),
    ):
        result = await run_oanda_bootstrap("token", "practice", "101-001-test")

    assert isinstance(result, OandaBootstrapResult)
    assert result.last_transaction_id == "566"
    assert len(result.lots) == 2
    assert {lot.broker_lot_id for lot in result.lots} == {"565", "553"}
    assert len(result.events) == 1
    assert result.events[0].broker_lot_id == "565"
    assert result.counts["bootstrap_open_lots"] == 1
    assert result.counts["bootstrap_closed_lots"] == 1
    assert result.counts["bootstrap_events"] == 1


@pytest.mark.asyncio
async def test_run_oanda_bootstrap_skips_closed_and_events_when_disabled():
    account = {"id": "101-001-test", "balance": "10000", "trades": []}

    with patch(
        "brokerai.trading.oanda_bootstrap.get_account_details",
        new=AsyncMock(return_value=(account, "566")),
    ), patch(
        "brokerai.trading.oanda_bootstrap.list_all_trades",
        new=AsyncMock(),
    ) as mock_closed, patch(
        "brokerai.trading.oanda_bootstrap.list_transactions_idrange",
        new=AsyncMock(),
    ) as mock_txns:
        result = await run_oanda_bootstrap(
            "token",
            "practice",
            "101-001-test",
            include_closed_trades=False,
            include_event_backfill=False,
        )

    mock_closed.assert_not_awaited()
    mock_txns.assert_not_awaited()
    assert result.lots == []
    assert result.events == []


@pytest.mark.asyncio
async def test_run_oanda_bootstrap_streams_events_via_sink():
    open_trade = {
        "id": "565",
        "instrument": "EUR_JPY",
        "state": "OPEN",
        "initialUnits": "-683",
        "currentUnits": "-683",
        "price": "184.196",
        "openTime": "2026-07-02T20:27:24.111844157Z",
    }
    account = {
        "id": "101-001-test",
        "balance": "10000",
        "trades": [open_trade],
    }
    page_one = [{"id": "565", "type": "ORDER_FILL", "time": "2026-07-02T20:27:24.111844157Z", "tradeID": "565"}]
    page_two = [{"id": "566", "type": "DAILY_FINANCING", "time": "2026-07-02T21:00:00.000000000Z"}]

    async def fake_iter(*_args, **_kwargs):
        yield page_one
        yield page_two

    sink_calls: list[int] = []

    async def capture_sink(batch, _protected):
        sink_calls.append(len(batch))

    with patch(
        "brokerai.trading.oanda_bootstrap.get_account_details",
        new=AsyncMock(return_value=(account, "566")),
    ), patch(
        "brokerai.trading.oanda_bootstrap.list_all_trades",
        new=AsyncMock(return_value=([], "566")),
    ), patch(
        "brokerai.trading.oanda_bootstrap.iter_transactions_idrange",
        new=fake_iter,
    ):
        result = await run_oanda_bootstrap(
            "token",
            "practice",
            "101-001-test",
            event_sink=capture_sink,
        )

    assert result.events_streamed is True
    assert result.events == []
    assert result.counts["bootstrap_events"] == 2
    assert sink_calls == [1, 1]
