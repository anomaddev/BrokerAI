from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from brokerai.bots.data_manager.candle_requirements import CandleRequirement
from brokerai.bots.data_manager.candles import fetch_and_cache_forex_candles, requirement_needs_bootstrap
from brokerai.bots.data_manager.service import DataManagerService
from brokerai.trading.data.models import SyncResult


def _service_with_repo(repo: AsyncMock) -> DataManagerService:
    cache = MagicMock()
    cache._market_repo = repo
    cache.sync = AsyncMock(return_value=SyncResult(symbol="EUR/USD", timeframe="M15", upserted=1))
    service = DataManagerService(cache=cache)
    return service


@pytest.mark.asyncio
async def test_requirement_needs_bootstrap_when_cache_short():
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    repo = AsyncMock()
    repo.count_candles.return_value = 10
    service = _service_with_repo(repo)
    assert await requirement_needs_bootstrap(requirement, service) is True


@pytest.mark.asyncio
async def test_requirement_needs_bootstrap_when_cache_full():
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    repo = AsyncMock()
    repo.count_candles.return_value = 100
    service = _service_with_repo(repo)
    assert await requirement_needs_bootstrap(requirement, service) is False


@pytest.mark.asyncio
async def test_fetch_and_cache_forex_candles_incremental():
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63, incremental=True)
    cache = MagicMock()
    cache.sync = AsyncMock(return_value=SyncResult(symbol="EUR/USD", timeframe="M15", upserted=1))
    cache._market_repo = AsyncMock()
    cache._market_repo.latest_candle_time.return_value = "2026-01-01T00:00:00.000000000Z"
    service = DataManagerService(cache=cache)

    result = await fetch_and_cache_forex_candles([requirement], service=service)

    assert result.candles_upserted == 1
    cache.sync.assert_awaited_once()
    assert cache.sync.await_args.kwargs["incremental"] is True


@pytest.mark.asyncio
async def test_fetch_and_cache_forex_candles_bootstrap():
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=200)
    cache = MagicMock()
    cache.sync = AsyncMock(return_value=SyncResult(symbol="EUR/USD", timeframe="M15", upserted=200))
    cache._market_repo = AsyncMock()
    cache._market_repo.latest_candle_time.return_value = "2026-01-01T00:00:00.000000000Z"
    service = DataManagerService(cache=cache)

    result = await fetch_and_cache_forex_candles([requirement], service=service)

    assert result.candles_upserted == 200
    cache.sync.assert_awaited_once()
    assert cache.sync.await_args.kwargs["bar_count"] == 200
