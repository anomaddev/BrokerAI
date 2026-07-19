from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.activity.constants import ACTION_PIPELINE_BATCH_COMPLETED
from brokerai.bots.secretary.activity import log_pipeline_batch_completed
from brokerai.bots.secretary.types import CandleJob, PipelineResult


@pytest.mark.asyncio
async def test_log_pipeline_batch_completed_records_metadata():
    jobs = [
        CandleJob(
            job_id="j1",
            asset_class="forex",
            symbol="EUR/USD",
            timeframe="M15",
            bar_count=100,
            trigger_time=datetime(2026, 7, 6, 12, 15, tzinfo=timezone.utc),
            strategies=(),
        ),
        CandleJob(
            job_id="j2",
            asset_class="forex",
            symbol="GBP/USD",
            timeframe="M15",
            bar_count=100,
            trigger_time=datetime(2026, 7, 6, 12, 15, tzinfo=timezone.utc),
            strategies=(),
        ),
    ]
    results = [
        PipelineResult(
            job_id="j1",
            ok=True,
            metadata={"latest_candle_time": "2026-07-06T12:00:00Z"},
        ),
        PipelineResult(job_id="j2", ok=False, error="fetch failed"),
    ]

    with patch(
        "brokerai.bots.secretary.activity.record_bot_activity",
        new_callable=AsyncMock,
    ) as record:
        await log_pipeline_batch_completed(jobs, results)

    record.assert_awaited_once()
    action_type, title, *_rest = record.await_args.args
    kwargs = record.await_args.kwargs
    assert action_type == ACTION_PIPELINE_BATCH_COMPLETED
    assert "2 jobs" in title
    assert kwargs["metadata"]["job_count"] == 2
    assert kwargs["metadata"]["ok_count"] == 1
    assert kwargs["metadata"]["failed_count"] == 1
    assert kwargs["metadata"]["timeframes"] == ["M15"]
    assert kwargs["metadata"]["latest_candle_times"] == ["2026-07-06T12:00:00Z"]
