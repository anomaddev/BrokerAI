from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.integrations import massive_cache


@pytest.fixture(autouse=True)
def _reset_cache():
    massive_cache.clear_market_status_cache()
    yield
    massive_cache.clear_market_status_cache()


@pytest.mark.asyncio
async def test_fetch_market_status_cached_coalesces_concurrent_requests():
    payload = {"serverTime": "2026-07-01T12:00:00Z", "currencies": {"fx": "open"}, "exchanges": {}}
    fetch = AsyncMock(return_value=(True, payload))

    with patch("brokerai.integrations.massive_cache.fetch_market_status", fetch):
        results = await asyncio.gather(
            massive_cache.fetch_market_status_cached("key-a"),
            massive_cache.fetch_market_status_cached("key-a"),
            massive_cache.fetch_market_status_cached("key-a"),
        )

    assert all(ok for ok, _ in results)
    assert all(data == payload for _, data in results)
    assert fetch.await_count == 1


@pytest.mark.asyncio
async def test_fetch_market_status_cached_serves_stale_on_rate_limit():
    payload = {"serverTime": "2026-07-01T12:00:00Z", "currencies": {"fx": "open"}, "exchanges": {}}
    fetch = AsyncMock(
        side_effect=[
            (True, payload),
            (False, "Massive returned HTTP 429"),
        ]
    )

    with patch("brokerai.integrations.massive_cache.fetch_market_status", fetch):
        ok1, data1 = await massive_cache.fetch_market_status_cached("key-a")
        assert ok1 and data1 == payload

        massive_cache._CACHE["expires_at"] = 0.0

        ok2, data2 = await massive_cache.fetch_market_status_cached("key-a")
        assert ok2 and data2 == payload
        assert fetch.await_count == 2
