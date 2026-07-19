from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.data.candle_cache import CandleCache
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_read_candles_with_since_and_until_uses_ascending_window():
    """Bounded trade lifecycle requests must not use find_latest_candles."""
    cache = CandleCache()
    cache._market_repo.find_candles = AsyncMock(return_value=[{"time": "t1"}])  # type: ignore[method-assign]
    cache._market_repo.find_latest_candles = AsyncMock(return_value=[])  # type: ignore[method-assign]

    rows = await cache.read_candles(
        "EUR/JPY",
        "M15",
        bar_count=96,
        since="2026-07-01T04:00:00+00:00",
        until="2026-07-01T14:00:00+00:00",
    )

    cache._market_repo.find_candles.assert_awaited_once()
    kwargs = cache._market_repo.find_candles.await_args.kwargs
    assert kwargs["ascending"] is True
    assert kwargs["limit"] == 96
    assert kwargs["since"] == "2026-07-01T04:00:00+00:00"
    assert kwargs["until"] == "2026-07-01T14:00:00+00:00"
    cache._market_repo.find_latest_candles.assert_not_awaited()
    assert rows == [{"time": "t1"}]


@pytest.mark.asyncio
async def test_request_candles_backfills_bounded_window():
    from brokerai.bots.data_manager.service import DataManagerService

    service = DataManagerService()
    service._cache.backfill = AsyncMock()  # type: ignore[method-assign]
    service._cache.read_candles = AsyncMock(return_value=[{"time": "t1"}])  # type: ignore[method-assign]
    service.ensure_coverage = AsyncMock()  # type: ignore[method-assign]

    since = "2026-07-01T04:00:00+00:00"
    until = "2026-07-01T14:00:00+00:00"
    rows = await service.request_candles(
        "EUR/JPY",
        "M15",
        bar_count=96,
        since=since,
        until=until,
        requester="test",
    )

    service._cache.backfill.assert_awaited_once_with(
        "EUR/JPY",
        "M15",
        since,
        until,
        source="oanda",
    )
    service.ensure_coverage.assert_not_awaited()
    assert rows == [{"time": "t1"}]


@pytest.mark.asyncio
async def test_fetch_count_from_oanda_uses_bar_count_not_cache():
    cache = CandleCache()
    cache._oanda_credentials = AsyncMock(return_value=("token", "practice"))  # type: ignore[method-assign]

    anchor = datetime(2026, 7, 5, 21, 30, tzinfo=timezone.utc)
    bar = {
        "time": "2026-07-05T21:30:00.000000000Z",
        "open": 1.1,
        "high": 1.2,
        "low": 1.0,
        "close": 1.15,
        "volume": 10,
    }

    with patch("brokerai.trading.data.candle_cache.fetch_candles_to", new_callable=AsyncMock) as mock_to:
        mock_to.return_value = [bar]
        rows = await cache.fetch_count_from_oanda(
            "USD/JPY",
            "M15",
            100,
            until=anchor,
        )

    mock_to.assert_awaited_once()
    assert mock_to.await_args.kwargs["count"] == 100
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_fetch_range_from_oanda_does_not_touch_cache():
    """Direct OANDA fetch must not read or write the candle cache."""
    cache = CandleCache()
    cache._oanda_credentials = AsyncMock(return_value=("token", "practice"))  # type: ignore[method-assign]
    cache._market_repo.upsert_candles = AsyncMock()  # type: ignore[method-assign]
    cache._market_repo.find_candles = AsyncMock()  # type: ignore[method-assign]

    with patch("brokerai.trading.data.candle_cache.fetch_candles_range", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {
                "time": "2026-07-01T10:00:00.000000000Z",
                "open": 1.1,
                "high": 1.2,
                "low": 1.0,
                "close": 1.15,
                "volume": 10,
            }
        ]
        rows = await cache.fetch_range_from_oanda(
            "EUR/USD",
            "M15",
            "2026-07-01T09:00:00+00:00",
            "2026-07-01T11:00:00+00:00",
        )

    mock_fetch.assert_awaited()
    cache._market_repo.upsert_candles.assert_not_awaited()
    cache._market_repo.find_candles.assert_not_awaited()
    assert len(rows) == 1
    assert rows[0]["time"] == "2026-07-01T10:00:00.000000000Z"
