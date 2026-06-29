from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from brokerai.bots.data_manager.service import DataManagerService
from brokerai.trading.data.models import SyncResult


@pytest.mark.asyncio
async def test_request_candles_triggers_sync_when_cache_short():
    cache = MagicMock()
    cache._market_repo = AsyncMock()
    cache._market_repo.count_candles.return_value = 0
    cache.is_cache_complete_up_to = AsyncMock(return_value=False)
    cache.sync = AsyncMock(return_value=SyncResult(symbol="EUR/USD", timeframe="M15", upserted=63, complete=True))
    cache.read_candles = AsyncMock(return_value=[{"time": "2026-01-01T00:00:00.000000000Z"}])
    service = DataManagerService(cache=cache)

    candles = await service.request_candles(
        "EUR/USD",
        "M15",
        bar_count=63,
        requester="test",
    )

    assert len(candles) == 1
    cache.sync.assert_awaited()
    assert ("EUR/USD", "M15", "oanda", 63) in service.registered_demand()


@pytest.mark.asyncio
async def test_request_candles_skips_sync_when_cache_ready():
    cache = MagicMock()
    cache._market_repo = AsyncMock()
    cache._market_repo.count_candles.return_value = 100
    cache.is_cache_complete_up_to = AsyncMock(return_value=True)
    cache.sync = AsyncMock()
    cache.read_candles = AsyncMock(return_value=[{"time": "2026-01-01T00:00:00.000000000Z"}])
    service = DataManagerService(cache=cache)

    await service.request_candles("EUR/USD", "M15", bar_count=63, requester="test")

    cache.sync.assert_not_awaited()
