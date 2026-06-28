from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.bots.data_manager.bot import DataManagerBot
from brokerai.bots.data_manager.candle_requirements import CandleRequirement
from brokerai.bots.data_manager.candles import requirement_needs_bootstrap


@pytest.mark.asyncio
async def test_requirement_needs_bootstrap_when_cache_short():
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    repo = AsyncMock()
    repo.count_candles.return_value = 10
    assert await requirement_needs_bootstrap(requirement, repo) is True


@pytest.mark.asyncio
async def test_requirement_needs_bootstrap_when_cache_full():
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    repo = AsyncMock()
    repo.count_candles.return_value = 100
    assert await requirement_needs_bootstrap(requirement, repo) is False


@pytest.mark.asyncio
async def test_plan_fetches_bootstraps_immediately():
    bot = DataManagerBot()
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    repo = AsyncMock()
    repo.count_candles.return_value = 0

    bootstrap, incremental, waiting = await bot._plan_fetches([requirement], repo)

    assert len(bootstrap) == 1
    assert incremental == []
    assert waiting == []


@pytest.mark.asyncio
async def test_plan_fetches_waits_for_next_close_when_cache_ready():
    bot = DataManagerBot()
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    repo = AsyncMock()
    repo.count_candles.return_value = 100

    bootstrap, incremental, waiting = await bot._plan_fetches([requirement], repo)

    assert bootstrap == []
    assert incremental == []
    assert len(waiting) == 1
    assert "M15" in bot._next_fetch_at


@pytest.mark.asyncio
async def test_plan_fetches_runs_incremental_when_due():
    bot = DataManagerBot()
    bot._next_fetch_at["M15"] = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    repo = AsyncMock()
    repo.count_candles.return_value = 100

    bootstrap, incremental, waiting = await bot._plan_fetches([requirement], repo)

    assert bootstrap == []
    assert len(incremental) == 1
    assert incremental[0].incremental is True
    assert waiting == []
