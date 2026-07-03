from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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


@pytest.mark.asyncio
async def test_find_candles_after_uses_gt_filter():
    repo = MarketDataRepository()
    rows = [
        {
            "meta": {"symbol": "EUR/USD", "timeframe": "M15", "source": "oanda"},
            "ts": datetime(2026, 1, 7, 15, 15, tzinfo=timezone.utc),
            "time": "2026-01-07T15:15:00.000000000Z",
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 0,
        }
    ]

    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=rows)
    find_cursor = MagicMock()
    find_cursor.sort.return_value.limit.return_value = cursor
    collection = MagicMock()
    collection.find.return_value = find_cursor
    db = {"market_data": collection}
    handle = AsyncMock()
    handle.db = db

    with patch("brokerai.db.repositories.market_data.get_db", AsyncMock(return_value=handle)):
        result = await repo.find_candles_after(
            "EUR/USD",
            "M15",
            "oanda",
            "2026-01-07T15:00:00.000000000Z",
            limit=5,
        )

    collection.find.assert_called_once_with(
        {
            "meta.symbol": "EUR/USD",
            "meta.timeframe": "M15",
            "meta.source": "oanda",
            "ts": {"$gt": datetime(2026, 1, 7, 15, 0, tzinfo=timezone.utc)},
        },
        {"_id": 0},
    )
    assert result == [
        {
            "symbol": "EUR/USD",
            "timeframe": "M15",
            "source": "oanda",
            "time": "2026-01-07T15:15:00.000000000Z",
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 0,
        }
    ]
