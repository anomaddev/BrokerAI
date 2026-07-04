from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.broker.state import BrokerStateService
from brokerai.trading.types import TradeIntent


@pytest.mark.asyncio
async def test_place_from_intent_paper_mode():
    intent = TradeIntent(
        strategy_id="s1",
        strategy_name="Test",
        pair="EUR/USD",
        asset_class="forex",
        direction="long",
        entry_price=1.1,
        stop_loss=1.09,
        take_profit=1.12,
        exit_mode="manual",
        risk_pct=1.0,
        units=1000,
        confidence=0.8,
    )
    lots_repo = AsyncMock()
    lots_repo.upsert_lot = AsyncMock(
        side_effect=lambda lot, **_: {
            "state": lot.state,
            "strategy_id": lot.strategy_id,
            "pair": intent.pair,
        }
    )
    with patch.object(BrokerStateService, "_credentials_for", return_value=(None, None)):
        saved = await BrokerStateService(lots_repo=lots_repo).place_from_intent("oanda", intent)

    assert saved["state"] == "open"
    assert saved["strategy_id"] == "s1"
    assert saved["pair"] == "EUR/USD"
    lots_repo.upsert_lot.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_instrument_exposure():
    service = BrokerStateService(lots_repo=AsyncMock())
    service._lots.list_open_lots = AsyncMock(
        return_value=[
            {
                "symbol": "EUR_USD",
                "pair": "EUR/USD",
                "direction": "long",
                "current_qty": 1000,
                "entry_price": 1.1,
                "unrealized_pl": 5.0,
                "broker_lot_id": "1",
            },
            {
                "symbol": "EUR_USD",
                "pair": "EUR/USD",
                "direction": "long",
                "current_qty": 500,
                "entry_price": 1.2,
                "unrealized_pl": 2.0,
                "broker_lot_id": "2",
            },
        ]
    )
    with patch.object(BrokerStateService, "_credentials_for", return_value=(None, None)):
        exposure = await service.get_instrument_exposure("oanda", "EUR_USD")
    assert exposure is not None
    assert exposure.total_qty == 1500
    assert len(exposure.broker_lot_ids) == 2
