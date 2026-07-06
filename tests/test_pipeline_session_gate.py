from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.bots.secretary.pipeline import PipelineRunner
from brokerai.bots.secretary.types import CandleJob, FetchStatus, PipelineContext
from brokerai.trading.types import AnalysisResult

# Weekday evening ET: Sydney session active, Asia/London/NY inactive.
_SYDNEY_ONLY = datetime(2026, 3, 4, 23, 0, tzinfo=timezone.utc)
# Weekday London window.
_LONDON_WINDOW = datetime(2026, 3, 4, 14, 0, tzinfo=timezone.utc)


def _strategy(
    strategy_id: str = "strategy-1",
    *,
    sessions: list[str] | None = None,
) -> dict:
    execution: dict = {"min_confidence": 60}
    if sessions is not None:
        execution["sessions"] = sessions
    return {
        "id": strategy_id,
        "name": "Test Strategy",
        "timeframe": "M15",
        "params": {
            "min_candles": 63,
            "signal": {"type": "ema_crossover"},
            "execution": execution,
        },
    }


@pytest.mark.asyncio
async def test_pipeline_runs_analysis_even_when_trading_session_inactive():
    """Trading sessions gate broker execution, not candle analysis."""
    strategy = _strategy()
    job = CandleJob(
        job_id="session-gate-1",
        asset_class="forex",
        symbol="EUR/USD",
        timeframe="M15",
        bar_count=63,
        trigger_time=_SYDNEY_ONLY,
        strategies=(strategy,),
        incremental=True,
        bootstrap=False,
    )
    context_after_fetch = PipelineContext.from_job(job)
    context_after_fetch.latest_candle_time = "2026-03-04T22:45:00.000000000Z"
    context_after_fetch.fetch_status = FetchStatus.OK

    analysis = AnalysisResult(
        strategy_id="strategy-1",
        strategy_name="Test Strategy",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.75,
        direction="long",
        min_candles=63,
        signal_type="ema_crossover",
    )

    broker = MagicMock()
    broker.process_analysis = AsyncMock(return_value=[])

    runner = PipelineRunner(broker=broker)

    with (
        patch(
            "brokerai.bots.secretary.pipeline.run_asset_data_manager",
            new_callable=AsyncMock,
            return_value=MagicMock(ok=True, data=context_after_fetch, metadata={"candles_upserted": 1}),
        ),
        patch(
            "brokerai.bots.secretary.pipeline.run_asset_analyst",
            new_callable=AsyncMock,
            return_value=MagicMock(ok=True, data=[analysis]),
        ) as run_analyst,
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_scheduled", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_fetch_started", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_fetch_completed", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_analyze_started", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_analyze_completed", new_callable=AsyncMock),
    ):
        result = await runner.run_job(job)

    assert result.ok
    assert len(result.analyses) == 1
    run_analyst.assert_awaited_once()
    broker.process_analysis.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_runs_analysis_when_trading_session_active():
    strategy = _strategy(sessions=["London", "NY"])
    job = CandleJob(
        job_id="session-gate-2",
        asset_class="forex",
        symbol="EUR/USD",
        timeframe="M15",
        bar_count=63,
        trigger_time=_LONDON_WINDOW,
        strategies=(strategy,),
        incremental=True,
        bootstrap=False,
    )
    context_after_fetch = PipelineContext.from_job(job)
    context_after_fetch.latest_candle_time = "2026-03-04T13:45:00.000000000Z"
    context_after_fetch.fetch_status = FetchStatus.OK

    analysis = AnalysisResult(
        strategy_id="strategy-1",
        strategy_name="Test Strategy",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.75,
        direction="long",
        min_candles=63,
        signal_type="ema_crossover",
    )

    broker = MagicMock()
    broker.process_analysis = AsyncMock(return_value=[])

    runner = PipelineRunner(broker=broker)

    with (
        patch(
            "brokerai.bots.secretary.pipeline.run_asset_data_manager",
            new_callable=AsyncMock,
            return_value=MagicMock(ok=True, data=context_after_fetch, metadata={"candles_upserted": 1}),
        ),
        patch(
            "brokerai.bots.secretary.pipeline.run_asset_analyst",
            new_callable=AsyncMock,
            return_value=MagicMock(ok=True, data=[analysis]),
        ) as run_analyst,
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_scheduled", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_fetch_started", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_fetch_completed", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_analyze_started", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_analyze_completed", new_callable=AsyncMock),
    ):
        result = await runner.run_job(job)

    assert result.ok
    assert len(result.analyses) == 1
    run_analyst.assert_awaited_once()
    broker.process_analysis.assert_awaited_once()
