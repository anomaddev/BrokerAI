from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.bots.secretary.bot import SecretaryBot
from brokerai.bots.secretary.candle_timeline import CandleTimeline
from brokerai.bots.secretary.pipeline import PipelineRunner
from brokerai.bots.secretary.types import CandleJob, FetchStatus, PipelineContext
from brokerai.config.settings import Settings
from brokerai.core.pipeline_candle_cache import PipelineCandleCache
from brokerai.core.worker_pool import WorkerPool
from brokerai.bots.base import EphemeralBot, WorkerResult
from brokerai.trading.types import AnalysisResult


class _EchoWorker(EphemeralBot[str, str]):
    name = "echo_worker"
    asset_class = "test"

    async def run(self, request: str) -> WorkerResult[str]:
        return WorkerResult(ok=True, data=request.upper())


def test_candle_job_dedupe_key():
    job = CandleJob(
        job_id="j1",
        asset_class="forex",
        symbol="EUR/USD",
        timeframe="M15",
        bar_count=100,
        trigger_time=datetime(2026, 1, 1, 12, 15, 3, tzinfo=timezone.utc),
        strategies=(),
    )
    assert "EUR/USD|M15|" in job.dedupe_key


def test_pipeline_context_from_job():
    job = CandleJob(
        job_id="j1",
        asset_class="forex",
        symbol="EUR/USD",
        timeframe="M15",
        bar_count=100,
        trigger_time=datetime(2026, 1, 1, 12, 15, 3, tzinfo=timezone.utc),
        strategies=({"id": "s1"},),
    )
    ctx = PipelineContext.from_job(job)
    assert ctx.symbol == "EUR/USD"
    assert len(ctx.strategies) == 1


@pytest.mark.asyncio
async def test_worker_pool_runs_ephemeral_worker():
    pool = WorkerPool()
    result = await pool.run(_EchoWorker, "hello", job_id="job-1")
    assert result.ok
    assert result.data == "HELLO"
    assert pool.active_count == 0


def test_pipeline_candle_cache_roundtrip():
    cache = PipelineCandleCache()
    candles = [{"time": "t", "close": 1.0}]
    ref = cache.store("EUR/USD", "M15", "2026-01-01T00:15:00Z", candles)
    assert cache.get(ref) == candles


def test_settings_secretary_defaults():
    assert Settings.model_fields["enabled_bots"].default == "secretary,broker,researcher"
    settings = Settings(enabled_bots="secretary,broker,researcher")
    assert settings.use_secretary_pipeline is True
    assert settings.enabled_bot_names == ["secretary", "broker", "researcher"]
    assert settings.pipeline_concurrency == 10
    assert settings.broker_sync_interval_seconds == 30


def test_candle_timeline_snapshot_next_fetches():
    timeline = CandleTimeline()
    fetches = timeline.snapshot_next_fetches()
    assert "M15" in fetches


def _sample_strategy() -> dict:
    return {
        "id": "strategy-1",
        "name": "Test Strategy",
        "timeframe": "M15",
        "params": {"min_candles": 63, "signal": {"type": "ema_crossover"}},
    }


@pytest.mark.asyncio
async def test_startup_pipeline_runs_analysis_and_broker():
    """Startup job should fetch, analyze, and hand results to the broker."""
    strategy = _sample_strategy()
    job = CandleJob(
        job_id="startup-1",
        asset_class="forex",
        symbol="EUR/USD",
        timeframe="M15",
        bar_count=63,
        trigger_time=datetime(2026, 1, 7, 15, 30, tzinfo=timezone.utc),
        strategies=(strategy,),
        incremental=False,
        bootstrap=True,
    )
    latest = "2026-01-07T15:15:00.000000000Z"
    context_after_fetch = PipelineContext.from_job(job)
    context_after_fetch.latest_candle_time = latest
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
            return_value=MagicMock(ok=True, data=context_after_fetch, metadata={"candles_upserted": 63}),
        ),
        patch(
            "brokerai.bots.secretary.pipeline.run_asset_analyst",
            new_callable=AsyncMock,
            return_value=MagicMock(ok=True, data=[analysis]),
        ),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_scheduled", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_fetch_started", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_fetch_completed", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_analyze_started", new_callable=AsyncMock),
        patch("brokerai.bots.secretary.pipeline.pipeline_activity.log_pipeline_analyze_completed", new_callable=AsyncMock),
    ):
        result = await runner.run_job(job)

    assert result.ok
    assert len(result.analyses) == 1
    broker.process_analysis.assert_awaited_once()
    passed_analyses, passed_context = broker.process_analysis.await_args.args
    assert passed_analyses[0].direction == "long"
    assert passed_context.symbol == "EUR/USD"


@pytest.mark.asyncio
async def test_secretary_run_startup_pass_dispatches_jobs():
    bot = SecretaryBot()
    job = CandleJob(
        job_id="startup-1",
        asset_class="forex",
        symbol="EUR/USD",
        timeframe="M15",
        bar_count=63,
        trigger_time=datetime(2026, 1, 7, 15, 30, tzinfo=timezone.utc),
        strategies=(_sample_strategy(),),
        incremental=False,
        bootstrap=True,
    )

    with (
        patch.object(
            bot._timeline,
            "build_startup_jobs",
            new_callable=AsyncMock,
            return_value=[job],
        ),
        patch.object(
            bot._pipeline,
            "run_jobs",
            new_callable=AsyncMock,
            return_value=[MagicMock(ok=True, duration_ms=100)],
        ) as run_jobs,
    ):
        await bot.run_startup_pass()

    assert bot._startup_done is True
    run_jobs.assert_awaited_once_with([job])

    # Second call is a no-op.
    await bot.run_startup_pass()
    assert run_jobs.await_count == 1
