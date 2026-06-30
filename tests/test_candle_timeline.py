from __future__ import annotations

from datetime import datetime, timezone
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
    service = AsyncMock()
    latest = "2026-01-01T00:15:00.000000000Z"
    service.latest_candle_time.return_value = latest
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
            "brokerai.bots.secretary.candle_timeline.requirement_needs_bootstrap",
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
    service = AsyncMock()
    latest = "2026-01-01T00:15:00.000000000Z"
    service.latest_candle_time.return_value = latest
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
