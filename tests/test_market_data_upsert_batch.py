"""Ensure candle upserts are chunked under asyncpg's bind-parameter limit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from brokerai.db.repositories import market_data as market_data_mod
from brokerai.db.repositories.market_data import MarketDataRepository

pytestmark = pytest.mark.usefixtures("sqlite_db")


def _candle(index: int) -> dict:
    when = datetime(2025, 1, 6, 13, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * index)
    price = 1.0 + index * 0.0001
    return {
        "time": when.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
        "open": price,
        "high": price + 0.0002,
        "low": price - 0.0002,
        "close": price + 0.0001,
        "volume": 1,
    }


@pytest.mark.asyncio
async def test_upsert_candles_chunks_large_batches(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(market_data_mod, "_UPSERT_BATCH_SIZE", 50)
    repo = MarketDataRepository()
    candles = [_candle(i) for i in range(125)]

    written = await repo.upsert_candles("EUR/USD", "M15", "oanda", candles)
    assert written == 125

    stored = await repo.find_candles("EUR/USD", "M15", "oanda")
    assert len(stored) == 125
    assert stored[0]["time"] == candles[0]["time"]
    assert stored[-1]["time"] == candles[-1]["time"]
