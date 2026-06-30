from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.bots.data_manager.candle_watch import collect_watch_requirements
from brokerai.db.repositories.candle_watch import CandleWatchRepository


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
    stored: dict[tuple[str, str, str, str], dict] = {}

    async def update_one(filter_doc, update_doc, upsert=False):
        key = (
            filter_doc["symbol"],
            filter_doc["timeframe"],
            filter_doc["source"],
            filter_doc["requester"],
        )
        if upsert or key in stored:
            stored[key] = {**filter_doc, **update_doc["$set"]}

    cursor = MagicMock()

    async def to_list(length=500):
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=300)
        return [
            doc
            for doc in stored.values()
            if doc.get("updated_at") and doc["updated_at"] >= cutoff
        ]

    cursor.to_list = AsyncMock(side_effect=to_list)
    collection = MagicMock()
    collection.update_one = AsyncMock(side_effect=update_one)
    collection.find.return_value = cursor
    db = MagicMock()
    db.__getitem__.return_value = collection
    handle = MagicMock()
    handle.db = db

    repo = CandleWatchRepository()

    with patch("brokerai.db.repositories.candle_watch.get_db", AsyncMock(return_value=handle)):
        await repo.upsert_watch("EUR/USD", "M15", "oanda", "web_explore", bar_count=120)
        active = await repo.list_active_watches(source="oanda")

    assert len(active) == 1
    assert active[0]["symbol"] == "EUR/USD"
    assert active[0]["bar_count"] == 120
