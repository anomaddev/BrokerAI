from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from brokerai.cost.categories import LLM
from brokerai.db.repositories.cost_ledger import CostLedgerRepository


pytestmark = pytest.mark.usefixtures("sqlite_db")


@pytest.mark.asyncio
async def test_cost_ledger_append_and_list_recent():
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

    items = await repo.list_recent(limit=10)
    assert len(items) == 1
    assert items[0]["description"].startswith("Forex analysis")


@pytest.mark.asyncio
async def test_cost_ledger_summarize_billable_only():
    now = datetime.now(timezone.utc)
    repo = CostLedgerRepository()
    await repo.append(
        LLM,
        1.25,
        "Billable call",
        metadata={"billable": True},
        occurred_at=now - timedelta(days=1),
    )
    await repo.append(
        LLM,
        9.99,
        "Non-billable call",
        metadata={"billable": False},
        occurred_at=now - timedelta(days=1),
    )

    all_summary = await repo.summarize(
        since=now - timedelta(days=7),
        until=now,
        billable_only=False,
    )
    assert all_summary["grand_total_usd"] == 11.24
    assert sum(item["count"] for item in all_summary["totals"]) == 2
