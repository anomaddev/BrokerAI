from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.data.candle_cache import CandleCache


@pytest.mark.asyncio
async def test_fetch_incremental_falls_back_when_from_request_misses_closed_bar():
    """Count-based fetch backfills stale cache when `from=latest` returns nothing new."""
    cache = CandleCache()
    latest = "2026-07-06T18:15:00.000000000Z"
    cache._market_repo.latest_candle_time = AsyncMock(return_value=latest)  # type: ignore[method-assign]

    new_bar = {
        "time": "2026-07-06T18:30:00.000000000Z",
        "open": 1.0,
        "high": 1.1,
        "low": 0.9,
        "close": 1.05,
        "volume": 100,
    }

    with (
        patch(
            "brokerai.trading.data.candle_cache.fetch_candles_from",
            new_callable=AsyncMock,
            return_value=[],
        ) as fetch_from,
        patch(
            "brokerai.trading.data.candle_cache.fetch_candles",
            new_callable=AsyncMock,
            return_value=[new_bar],
        ) as fetch_count,
    ):
        candles = await cache._fetch_incremental(
            "EUR/USD",
            "M15",
            token="token",
            environment="practice",
            instrument="EUR_USD",
            granularity="M15",
        )

    fetch_from.assert_awaited_once()
    fetch_count.assert_awaited_once()
    assert candles == [new_bar]
