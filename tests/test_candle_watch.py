from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from brokerai.bots.data_manager.candle_watch import collect_watch_requirements
from brokerai.db.repositories.candle_watch import CandleWatchRepository


pytestmark = pytest.mark.usefixtures("sqlite_db")


@pytest.mark.asyncio
async def test_collect_watch_requirements_merges_bar_counts():
    watches = [
        {
            "symbol": "EUR/USD",
            "timeframe": "M15",
            "source": "oanda",
            "requester": "web_explore",
            "bar_count": 120,
        },
        {
            "symbol": "EUR/USD",
            "timeframe": "M15",
            "source": "oanda",
            "requester": "other",
            "bar_count": 200,
        },
    ]

    with patch.object(CandleWatchRepository, "list_active_watches", AsyncMock(return_value=watches)):
        requirements = await collect_watch_requirements()

    assert len(requirements) == 1
    assert requirements[0].pairs == ("EUR/USD",)
    assert requirements[0].timeframe == "M15"
    assert requirements[0].bar_count == 200


@pytest.mark.asyncio
async def test_candle_watch_repository_upsert_and_list_active():
    repo = CandleWatchRepository()

    await repo.upsert_watch("EUR/USD", "M15", "oanda", "web_explore", bar_count=120)
    active = await repo.list_active_watches(source="oanda")

    assert len(active) == 1
    assert active[0]["symbol"] == "EUR/USD"
    assert active[0]["bar_count"] == 120
