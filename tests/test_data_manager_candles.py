from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from brokerai.bots.data_manager.candle_requirements import CandleRequirement
from brokerai.bots.data_manager.candles import _fetch_pair_candles


@pytest.mark.asyncio
async def test_fetch_pair_candles_uses_strategy_bar_count_for_forward_fetch():
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63, incremental=True)
    repo = AsyncMock()
    repo.count_candles.return_value = 100
    repo.latest_candle_time.return_value = "2026-01-01T00:00:00.000000000Z"
    repo.earliest_candle_time.return_value = "2025-12-01T00:00:00.000000000Z"

    with (
        patch(
            "brokerai.bots.data_manager.candles.fetch_candles_from",
            new_callable=AsyncMock,
            return_value=[],
        ) as fetch_from,
        patch(
            "brokerai.bots.data_manager.candles.fetch_candles_to",
            new_callable=AsyncMock,
        ) as fetch_to,
        patch(
            "brokerai.bots.data_manager.candles.fetch_candles",
            new_callable=AsyncMock,
        ) as fetch_initial,
    ):
        candles, error = await _fetch_pair_candles(
            "EUR/USD",
            requirement,
            access_token="token",
            environment="practice",
            repo=repo,
        )

    assert error is None
    assert candles == []
    fetch_from.assert_awaited_once()
    assert fetch_from.await_args.kwargs["count"] == 2
    fetch_to.assert_not_awaited()
    fetch_initial.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_pair_candles_uses_strategy_bar_count_for_initial_fetch():
    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=200)
    repo = AsyncMock()
    repo.count_candles.return_value = 0
    repo.latest_candle_time.return_value = None

    with (
        patch(
            "brokerai.bots.data_manager.candles.fetch_candles",
            new_callable=AsyncMock,
            return_value=[{"time": "2026-01-01T00:00:00.000000000Z", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0}],
        ) as fetch_initial,
        patch(
            "brokerai.bots.data_manager.candles.fetch_candles_from",
            new_callable=AsyncMock,
        ) as fetch_from,
    ):
        candles, error = await _fetch_pair_candles(
            "EUR/USD",
            requirement,
            access_token="token",
            environment="practice",
            repo=repo,
        )

    assert error is None
    assert len(candles) == 1
    fetch_initial.assert_awaited_once()
    assert fetch_initial.await_args.args[4] == 200
    fetch_from.assert_not_awaited()
