from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.cost.categories import LLM
from brokerai.db.repositories.cost_ledger import CostLedgerRepository


@pytest.mark.asyncio
async def test_cost_ledger_append_and_list_recent():
    stored: list[dict] = []

    async def insert_one(doc):
        stored.append(doc)

    fake_collection = MagicMock()
    fake_collection.insert_one = AsyncMock(side_effect=insert_one)
    fake_collection.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=stored
    )

    class FakeDB:
        def __getitem__(self, key: str):
            assert key == CostLedgerRepository.COLLECTION
            return fake_collection

    with patch(
        "brokerai.db.repositories.cost_ledger.get_db",
        AsyncMock(return_value=MagicMock(db=FakeDB())),
    ):
        repo = CostLedgerRepository()
        row = await repo.append(
            LLM,
            0.0042,
            "Forex analysis — EUR (gpt-4o)",
            source="daily_report",
            metadata={"input_tokens": 1000, "output_tokens": 200, "billable": True},
        )

    assert row["category"] == LLM
    assert row["amount_usd"] == 0.0042
    assert row["source"] == "daily_report"
    assert row["metadata"]["input_tokens"] == 1000
    assert row["occurred_at"].endswith("+00:00") or row["occurred_at"].endswith("Z")

    fake_collection.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=stored
    )
    with patch(
        "brokerai.db.repositories.cost_ledger.get_db",
        AsyncMock(return_value=MagicMock(db=FakeDB())),
    ):
        items = await repo.list_recent(limit=10)

    assert len(items) == 1
    assert items[0]["description"].startswith("Forex analysis")


@pytest.mark.asyncio
async def test_cost_ledger_summarize_billable_only():
    now = datetime.now(timezone.utc)

    def aggregate(pipeline):
        match_stage = pipeline[0].get("$match", {}) if pipeline else {}
        assert match_stage.get("metadata.billable") == {"$ne": False}
        cursor = MagicMock()
        cursor.to_list = AsyncMock(
            return_value=[
                {"_id": LLM, "amount_usd": 1.25, "count": 3},
            ]
        )
        return cursor

    fake_collection = MagicMock()
    fake_collection.aggregate = aggregate

    class FakeDB:
        def __getitem__(self, key: str):
            assert key == CostLedgerRepository.COLLECTION
            return fake_collection

    with patch(
        "brokerai.db.repositories.cost_ledger.get_db",
        AsyncMock(return_value=MagicMock(db=FakeDB())),
    ):
        repo = CostLedgerRepository()
        summary = await repo.summarize(
            since=now - timedelta(days=7),
            until=now,
            billable_only=True,
        )

    assert summary["grand_total_usd"] == 1.25
    assert summary["totals"] == [{"category": LLM, "amount_usd": 1.25, "count": 3}]
