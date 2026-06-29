from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from brokerai.db.repositories.market_data import MarketDataRepository


@pytest.mark.asyncio
async def test_find_latest_candles_returns_newest_window():
    repo = MarketDataRepository()
    rows_desc = [
        {"time": "2026-01-01T23:00:00.000000000Z", "close": 3.0},
        {"time": "2026-01-01T22:00:00.000000000Z", "close": 2.0},
        {"time": "2026-01-01T21:00:00.000000000Z", "close": 1.0},
    ]
    repo.find_candles = AsyncMock(return_value=rows_desc)  # type: ignore[method-assign]

    latest = await repo.find_latest_candles("EUR/USD", "M15", "oanda", limit=3)

    repo.find_candles.assert_awaited_once()
    assert repo.find_candles.await_args.kwargs["ascending"] is False
    assert len(latest) == 3
    assert latest[0]["time"] == "2026-01-01T21:00:00.000000000Z"
    assert latest[-1]["time"] == "2026-01-01T23:00:00.000000000Z"
