from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from brokerai.db.repositories.market_data import MarketDataRepository


pytestmark = pytest.mark.usefixtures("sqlite_db")


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


@pytest.mark.asyncio
async def test_find_candles_after_uses_gt_filter():
    repo = MarketDataRepository()
    fetched_at = datetime(2026, 1, 7, 15, 0, tzinfo=timezone.utc)
    await repo.upsert_candles(
        "EUR/USD",
        "M15",
        "oanda",
        [
            {
                "time": "2026-01-07T15:15:00.000000000Z",
                "open": 1.1,
                "high": 1.2,
                "low": 1.0,
                "close": 1.15,
                "volume": 0,
                "fetched_at": fetched_at,
            }
        ],
    )

@pytest.mark.asyncio
async def test_find_candles_after_uses_gt_filter():
    repo = MarketDataRepository()
    fetched_at = datetime(2026, 1, 7, 15, 0, tzinfo=timezone.utc)
    await repo.upsert_candles(
        "EUR/USD",
        "M15",
        "oanda",
        [
            {
                "time": "2026-01-07T15:15:00.000000000Z",
                "open": 1.1,
                "high": 1.2,
                "low": 1.0,
                "close": 1.15,
                "volume": 0,
                "fetched_at": fetched_at,
            }
        ],
    )

    result = await repo.find_candles_after(
        "EUR/USD",
        "M15",
        "oanda",
        "2026-01-07T15:00:00.000000000Z",
        limit=5,
    )

    assert len(result) == 1
    assert result[0]["time"] == "2026-01-07T15:15:00.000000000Z"
    assert result[0]["close"] == 1.15
