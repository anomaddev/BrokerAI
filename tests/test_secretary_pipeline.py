from __future__ import annotations

from datetime import datetime, timezone

import pytest

from brokerai.bots.secretary.candle_timeline import CandleTimeline
from brokerai.bots.secretary.types import CandleJob, PipelineContext
from brokerai.config.settings import Settings
from brokerai.core.pipeline_candle_cache import PipelineCandleCache
from brokerai.core.worker_pool import WorkerPool
from brokerai.bots.base import EphemeralBot, WorkerResult


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
    settings = Settings()
    assert settings.use_secretary_pipeline is True
    assert settings.pipeline_concurrency == 10
    assert settings.broker_sync_interval_seconds == 30


def test_candle_timeline_snapshot_next_fetches():
    timeline = CandleTimeline()
    fetches = timeline.snapshot_next_fetches()
    assert "M15" in fetches
