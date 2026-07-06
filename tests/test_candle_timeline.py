from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.bots.data_manager.candle_requirements import CandleRequirement
from brokerai.bots.secretary.candle_timeline import CandleTimeline
from brokerai.trading.candle_revision import GLOBAL_CANDLE_REVISIONS


def _strategy(*, strategy_id: str = "strategy-1") -> dict:
    return {
        "id": strategy_id,
        "name": "Test Strategy",
        "timeframe": "M15",
        "asset_class": "forex",
        "instruments": ["EUR/USD"],
        "instrument_selection": {"forex": ["EUR/USD"]},
        "params": {"min_candles": 63},
    }


@pytest.mark.asyncio
async def test_fetch_due_job_runs_before_new_candle_visible():
    """Scheduled fetches must not be skipped by a pre-fetch revision check."""
    timeline = CandleTimeline()
    service = MagicMock()
    service.registered_demand.return_value = []
    service.cache = MagicMock()
    service.cache.is_cache_complete_up_to = AsyncMock(return_value=True)
    latest = "2026-01-01T00:15:00.000000000Z"
    service.latest_candle_time = AsyncMock(return_value=latest)
    GLOBAL_CANDLE_REVISIONS.mark_updated("EUR/USD", "M15", latest)

    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    strategy = _strategy()
    when = datetime(2026, 1, 1, 0, 15, 5, tzinfo=timezone.utc)
    timeline._next_fetch_at["M15"] = datetime(2026, 1, 1, 0, 15, 3, tzinfo=timezone.utc)

    load_result = MagicMock(
        skip_reason=None,
        strategies=[(strategy, ["EUR/USD"])],
    )
    runtime = MagicMock()
    runtime.build_work_plan.return_value = MagicMock(
        units=[
            MagicMock(
                pair="EUR/USD",
                timeframe="M15",
                bar_count=63,
                asset_class="forex",
                strategies=(strategy,),
            )
        ]
    )

    with (
        patch(
            "brokerai.bots.secretary.candle_timeline.load_runnable_forex_strategies",
            new_callable=AsyncMock,
            return_value=load_result,
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.collect_watch_requirements",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.collect_candle_requirements",
            return_value=([requirement], []),
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.requirement_needs_warmup",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.get_asset_runtime",
            return_value=runtime,
        ),
    ):
        jobs, _warnings = await timeline.build_due_jobs(service, now=when)

    assert len(jobs) == 1
    assert jobs[0].symbol == "EUR/USD"
    assert jobs[0].timeframe == "M15"
    assert len(jobs[0].strategies) == 1


@pytest.mark.asyncio
async def test_analysis_only_job_skips_when_revision_unchanged():
    """Catch-up analysis jobs should still honor revision gating."""
    timeline = CandleTimeline()
    service = MagicMock()
    service.registered_demand.return_value = []
    service.cache = MagicMock()
    service.cache.is_cache_complete_up_to = AsyncMock(return_value=True)
    latest = "2026-01-01T00:15:00.000000000Z"
    service.latest_candle_time = AsyncMock(return_value=latest)
    GLOBAL_CANDLE_REVISIONS.mark_updated("EUR/USD", "M15", latest)

    strategy = _strategy()
    when = datetime(2026, 1, 1, 0, 20, 0, tzinfo=timezone.utc)
    timeline._next_fetch_at["M15"] = datetime(2026, 1, 1, 0, 30, 3, tzinfo=timezone.utc)

    load_result = MagicMock(
        skip_reason=None,
        strategies=[(strategy, ["EUR/USD"])],
    )
    runtime = MagicMock()
    runtime.build_work_plan.return_value = MagicMock(
        units=[
            MagicMock(
                pair="EUR/USD",
                timeframe="M15",
                bar_count=63,
                asset_class="forex",
                strategies=(strategy,),
            )
        ]
    )

    with (
        patch(
            "brokerai.bots.secretary.candle_timeline.load_runnable_forex_strategies",
            new_callable=AsyncMock,
            return_value=load_result,
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.collect_watch_requirements",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.collect_candle_requirements",
            return_value=([], []),
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.get_asset_runtime",
            return_value=runtime,
        ),
    ):
        jobs, _warnings = await timeline.build_due_jobs(service, now=when)

    assert jobs == []


@pytest.mark.asyncio
async def test_due_jobs_run_bootstrap_when_warmup_needed_at_fetch_due():
    """Scheduled fetches should warm up short cache instead of waiting for startup only."""
    timeline = CandleTimeline()
    service = MagicMock()
    service.registered_demand.return_value = []
    service.cache = MagicMock()
    service.cache._market_repo.count_candles = AsyncMock(return_value=10)
    service.latest_candle_time = AsyncMock(return_value="2026-01-01T00:00:00.000000000Z")

    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    strategy = _strategy()
    when = datetime(2026, 1, 1, 0, 15, 5, tzinfo=timezone.utc)
    timeline._next_fetch_at["M15"] = datetime(2026, 1, 1, 0, 15, 3, tzinfo=timezone.utc)

    load_result = MagicMock(
        skip_reason=None,
        strategies=[(strategy, ["EUR/USD"])],
    )

    with (
        patch(
            "brokerai.bots.secretary.candle_timeline.load_runnable_forex_strategies",
            new_callable=AsyncMock,
            return_value=load_result,
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.collect_watch_requirements",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.collect_candle_requirements",
            return_value=([requirement], []),
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.requirement_needs_warmup",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        jobs, _warnings = await timeline.build_due_jobs(service, now=when)

    assert len(jobs) == 1
    assert jobs[0].bootstrap is True
    assert jobs[0].incremental is False


@pytest.mark.asyncio
async def test_due_jobs_run_incremental_when_cache_stale_at_fetch_due():
    """Stale cache with enough bars should still fetch on the candle schedule."""
    timeline = CandleTimeline()
    service = MagicMock()
    service.registered_demand.return_value = []
    service.cache = MagicMock()
    service.cache.is_cache_complete_up_to = AsyncMock(return_value=False)
    service.latest_candle_time = AsyncMock(return_value="2026-01-01T00:00:00.000000000Z")

    requirement = CandleRequirement(timeframe="M15", pairs=("EUR/USD",), bar_count=63)
    strategy = _strategy()
    when = datetime(2026, 1, 1, 0, 15, 5, tzinfo=timezone.utc)
    timeline._next_fetch_at["M15"] = datetime(2026, 1, 1, 0, 15, 3, tzinfo=timezone.utc)

    load_result = MagicMock(
        skip_reason=None,
        strategies=[(strategy, ["EUR/USD"])],
    )
    runtime = MagicMock()
    runtime.build_work_plan.return_value = MagicMock(
        units=[
            MagicMock(
                pair="EUR/USD",
                timeframe="M15",
                bar_count=63,
                asset_class="forex",
                strategies=(strategy,),
            )
        ]
    )

    with (
        patch(
            "brokerai.bots.secretary.candle_timeline.load_runnable_forex_strategies",
            new_callable=AsyncMock,
            return_value=load_result,
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.collect_watch_requirements",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.collect_candle_requirements",
            return_value=([requirement], []),
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.requirement_needs_warmup",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.get_asset_runtime",
            return_value=runtime,
        ),
    ):
        jobs, _warnings = await timeline.build_due_jobs(service, now=when)

    assert len(jobs) == 1
    assert jobs[0].bootstrap is False
    assert jobs[0].incremental is True


@pytest.mark.asyncio
async def test_startup_jobs_bootstrap_stale_cache():
    """Startup warm-up should full-sync stale cache, not incremental catch-up."""
    timeline = CandleTimeline()
    service = MagicMock()
    service.latest_candle_time = AsyncMock(return_value="2026-01-01T00:00:00.000000000Z")

    strategy = _strategy()
    load_result = MagicMock(
        skip_reason=None,
        strategies=[(strategy, ["EUR/USD"])],
    )
    runtime = MagicMock()
    runtime.build_work_plan.return_value = MagicMock(
        units=[
            MagicMock(
                pair="EUR/USD",
                timeframe="M15",
                bar_count=63,
                asset_class="forex",
                strategies=(strategy,),
            )
        ]
    )

    with (
        patch(
            "brokerai.bots.secretary.candle_timeline.load_runnable_forex_strategies",
            new_callable=AsyncMock,
            return_value=load_result,
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.get_asset_runtime",
            return_value=runtime,
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.requirement_needs_bootstrap",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        jobs = await timeline.build_startup_jobs(service)

    assert len(jobs) == 1
    assert jobs[0].bootstrap is True
    assert jobs[0].incremental is False
    assert "M15" in timeline._next_fetch_at


@pytest.mark.asyncio
async def test_due_jobs_idle_cache_avoids_repeated_strategy_loads():
    """When nothing can run, log once and skip MongoDB strategy reloads between rechecks."""
    timeline = CandleTimeline()
    service = MagicMock()
    service.registered_demand.return_value = []

    load_result = MagicMock(skip_reason="no enabled strategies", strategies=[])

    with (
        patch(
            "brokerai.bots.secretary.candle_timeline.load_runnable_forex_strategies",
            new_callable=AsyncMock,
            return_value=load_result,
        ) as load_strategies,
        patch(
            "brokerai.bots.secretary.candle_timeline.collect_watch_requirements",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        jobs, warnings = await timeline.build_due_jobs(service)
        assert jobs == []
        assert warnings == ["no enabled strategies"]
        assert load_strategies.await_count == 1

        jobs, warnings = await timeline.build_due_jobs(service)
        assert jobs == []
        assert warnings == []
        assert load_strategies.await_count == 1

        when = datetime.now(timezone.utc) + timedelta(seconds=61)
        jobs, warnings = await timeline.build_due_jobs(service, now=when)
        assert jobs == []
        assert warnings == []
        assert load_strategies.await_count == 2


@pytest.mark.asyncio
async def test_due_jobs_idle_cache_clears_when_demand_registered():
    timeline = CandleTimeline()
    service = MagicMock()
    service.registered_demand.return_value = []

    load_result = MagicMock(skip_reason="no enabled strategies", strategies=[])

    with (
        patch(
            "brokerai.bots.secretary.candle_timeline.load_runnable_forex_strategies",
            new_callable=AsyncMock,
            return_value=load_result,
        ) as load_strategies,
        patch(
            "brokerai.bots.secretary.candle_timeline.collect_watch_requirements",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "brokerai.bots.secretary.candle_timeline.requirement_needs_warmup",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        await timeline.build_due_jobs(service)
        assert load_strategies.await_count == 1

        service.registered_demand.return_value = [("EUR/USD", "M15", "oanda", 63)]
        await timeline.build_due_jobs(service)
        assert load_strategies.await_count == 2
        assert timeline._pipeline_idle_reason is None
