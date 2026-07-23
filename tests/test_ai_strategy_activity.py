"""AI Strategy activity log aggregation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from brokerai.ai_strategy.activity import _digest_summary, build_ai_strategy_activity
from brokerai.ai_strategy.lifecycle import ensure_lifecycle_on_create
from brokerai.db.repositories.ai_strategy_startup import AiStrategyStartupJobsRepository
from brokerai.db.repositories.backtest_runs import BacktestRunsRepository
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.db.repositories.strategy_learning import StrategyMemoryDigestsRepository
from brokerai.strategies.presets.ai_strategy.definition import DEFAULT_PARAMS


pytestmark = pytest.mark.usefixtures("sqlite_db")


async def _create_ai(name: str = "AI Log", symbol: str = "EUR/USD") -> dict:
    return await StrategiesRepository().create(
        name=name,
        description="",
        preset_id="ai_strategy",
        params=dict(DEFAULT_PARAMS),
        instrument_selection={"forex": [symbol]},
        enabled=False,
    )


@pytest.mark.asyncio
async def test_activity_rejects_non_ai_strategy():
    from brokerai.strategies.presets.ema_crossover.definition import (
        DEFAULT_PARAMS as EMA_DEFAULT_PARAMS,
    )

    created = await StrategiesRepository().create(
        name="EMA",
        description="",
        preset_id="ema_crossover",
        params=dict(EMA_DEFAULT_PARAMS),
        instrument_selection={"forex": ["EUR/USD"]},
    )
    with pytest.raises(ValueError, match="Not an AI Strategy"):
        await build_ai_strategy_activity(created["id"])


@pytest.mark.asyncio
async def test_activity_aggregates_startup_digest_backtest():
    strategy = await _create_ai()
    sid = strategy["id"]

    await AiStrategyStartupJobsRepository().enqueue(
        sid,
        {
            "loop_target": 2,
            "required_reports": ["daily"],
            "phase": "ensuring_reports",
        },
    )
    await StrategyMemoryDigestsRepository().create_version(
        sid,
        {
            "standing_rules": ["Prefer London continuation"],
            "anti_rules": ["Avoid late NY chase"],
            "summary": "Continuation bias",
            "source": "ai_strategy_startup_seed",
        },
        version=1,
    )

    await BacktestRunsRepository().create_queued_runs(
        [strategy],
        name="Startup loop 1",
        instrument="EUR/USD",
        period="6m",
        origin="ai_strategy_startup",
        digest_version="1",
    )

    # Mark warm-up ready for lifecycle event.
    from brokerai.db.pg.client import session_scope
    from brokerai.db.pg.models import StrategyRow
    from brokerai.db.repositories.strategies import _sync_row_columns

    ready_at = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc).isoformat()
    async with session_scope() as session:
        row = await session.get(StrategyRow, sid)
        assert row is not None
        doc = dict(row.doc)
        doc = ensure_lifecycle_on_create(doc, default_warmup_trading_days=5)
        doc["execution_phase"] = "ready"
        doc["warmup"] = {**(doc.get("warmup") or {}), "ready_at": ready_at, "completed_days": 5}
        _sync_row_columns(row, doc)

    payload = await build_ai_strategy_activity(sid, limit=50)
    assert payload is not None
    assert payload["strategy"]["id"] == sid
    assert payload["startup_job"] is not None
    assert payload["latest_digest"] is not None
    assert payload["latest_digest"]["standing_rule_count"] == 1
    assert payload["latest_digest"]["standing_rules"] == ["Prefer London continuation"]
    assert payload["latest_digest"]["anti_rules"] == ["Avoid late NY chase"]

    kinds = {event["kind"] for event in payload["events"]}
    assert "startup" in kinds
    assert "digest" in kinds
    assert "backtest" in kinds
    assert "lifecycle" in kinds

    titles = [event["title"] for event in payload["events"]]
    assert any("Startup" in title for title in titles)
    assert any("Memory digest" in title for title in titles)
    assert any("Signal review" in title for title in titles)
    assert any("ready to promote" in title.lower() for title in titles)


@pytest.mark.asyncio
async def test_activity_missing_strategy():
    assert await build_ai_strategy_activity("missing") is None


def test_digest_summary_flattens_rule_objects():
    summary = _digest_summary(
        {
            "id": "d1",
            "version": 2,
            "standing_rules": [
                {"kind": "standing_rule", "text": "Bias long on carry"},
                "legacy string rule",
                {"kind": "standing_rule", "text": ""},
            ],
            "anti_rules": [{"kind": "anti_rule", "text": "Do not chase"}],
            "summary": "ok",
        }
    )
    assert summary is not None
    assert summary["standing_rules"] == ["Bias long on carry", "legacy string rule"]
    assert summary["anti_rules"] == ["Do not chase"]
    assert summary["standing_rule_count"] == 3
    assert summary["anti_rule_count"] == 1
