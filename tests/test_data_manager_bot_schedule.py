from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from brokerai.bots.data_manager.bot import DataManagerBot
from brokerai.bots.data_manager.candle_requirements import CandleRequirement
from brokerai.bots.data_manager.candles import requirement_needs_bootstrap


def _mock_service(count: int) -> MagicMock:
    repo = AsyncMock()
    repo.count_candles.return_value = count
    cache = MagicMock()
    cache._market_repo = repo
    service = MagicMock()
    service.cache = cache
    service.registered_demand.return_value = []
    return service


@pytest.mark.asyncio
async def test_requirement_needs_bootstrap_when_cache_short():
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    service = _mock_service(10)
    assert await requirement_needs_bootstrap(requirement, service) is True


@pytest.mark.asyncio
async def test_requirement_needs_bootstrap_when_cache_full():
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    service = _mock_service(100)
    assert await requirement_needs_bootstrap(requirement, service) is False


@pytest.mark.asyncio
async def test_plan_fetches_bootstraps_immediately():
    bot = DataManagerBot()
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    bot._service = _mock_service(0)

    bootstrap, incremental, waiting = await bot._plan_fetches([requirement])

    assert len(bootstrap) == 1
    assert len(incremental) == 1
    assert incremental[0].incremental is True
    assert waiting == []


@pytest.mark.asyncio
async def test_plan_fetches_runs_initial_incremental_when_cache_ready():
    bot = DataManagerBot()
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    bot._service = _mock_service(100)

    bootstrap, incremental, waiting = await bot._plan_fetches([requirement])

    assert bootstrap == []
    assert len(incremental) == 1
    assert incremental[0].incremental is True
    assert waiting == []
    assert "M15" in bot._next_fetch_at


@pytest.mark.asyncio
async def test_plan_fetches_waits_for_next_close_when_cache_ready():
    bot = DataManagerBot()
    bot._next_fetch_at["M15"] = datetime(2099, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    bot._service = _mock_service(100)

    bootstrap, incremental, waiting = await bot._plan_fetches([requirement])

    assert bootstrap == []
    assert incremental == []
    assert len(waiting) == 1


@pytest.mark.asyncio
async def test_plan_fetches_runs_incremental_when_due():
    bot = DataManagerBot()
    bot._next_fetch_at["M15"] = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    bot._service = _mock_service(100)

    bootstrap, incremental, waiting = await bot._plan_fetches([requirement])

    assert bootstrap == []
    assert len(incremental) == 1
    assert incremental[0].incremental is True
    assert waiting == []
