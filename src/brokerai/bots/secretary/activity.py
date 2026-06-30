from __future__ import annotations

from typing import Any

from brokerai.activity.constants import (
    ACTION_ACCOUNT_SUMMARY_UPDATED,
    ACTION_PIPELINE_ANALYZE_COMPLETED,
    ACTION_PIPELINE_ANALYZE_STARTED,
    ACTION_PIPELINE_ASSOCIATE_COMPLETED,
    ACTION_PIPELINE_ASSOCIATE_STARTED,
    ACTION_PIPELINE_BROKER_COMPLETED,
    ACTION_PIPELINE_BROKER_STARTED,
    ACTION_PIPELINE_FAILED,
    ACTION_PIPELINE_FETCH_COMPLETED,
    ACTION_PIPELINE_FETCH_STARTED,
    ACTION_PIPELINE_SCHEDULED,
    ACTION_PIPELINE_SKIPPED,
)
from brokerai.activity.log import record_bot_activity
from brokerai.bots.secretary.types import PipelineContext


def _base_metadata(context: PipelineContext, **extra: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "job_id": context.job_id,
        "symbol": context.symbol,
        "timeframe": context.timeframe,
        "asset_class": context.asset_class,
    }
    if context.latest_candle_time:
        meta["latest_candle_time"] = context.latest_candle_time
    meta.update(extra)
    return meta


async def log_pipeline_scheduled(context: PipelineContext) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_SCHEDULED,
        f"Pipeline scheduled: {context.symbol} {context.timeframe}",
        source="secretary",
        metadata=_base_metadata(context),
    )


async def log_pipeline_skipped(context: PipelineContext, reason: str) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_SKIPPED,
        f"Pipeline skipped: {context.symbol} {context.timeframe}",
        detail=reason,
        source="secretary",
        metadata=_base_metadata(context, reason=reason),
    )


async def log_pipeline_fetch_started(context: PipelineContext) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_FETCH_STARTED,
        f"Fetching candles: {context.symbol} {context.timeframe}",
        source="secretary",
        metadata=_base_metadata(context),
    )


async def log_pipeline_fetch_completed(context: PipelineContext, duration_ms: int) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_FETCH_COMPLETED,
        f"Fetch complete: {context.symbol} {context.timeframe}",
        source="secretary",
        metadata=_base_metadata(context, duration_ms=duration_ms, fetch_status=context.fetch_status.value),
    )


async def log_pipeline_analyze_started(context: PipelineContext) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_ANALYZE_STARTED,
        f"Analyzing: {context.symbol} {context.timeframe}",
        source="secretary",
        metadata=_base_metadata(context),
    )


async def log_pipeline_analyze_completed(
    context: PipelineContext,
    duration_ms: int,
    *,
    result_count: int,
) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_ANALYZE_COMPLETED,
        f"Analysis complete: {context.symbol} {context.timeframe}",
        source="secretary",
        metadata=_base_metadata(context, duration_ms=duration_ms, result_count=result_count),
    )


async def log_pipeline_broker_started(context: PipelineContext) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_BROKER_STARTED,
        f"Broker processing: {context.symbol} {context.timeframe}",
        source="secretary",
        metadata=_base_metadata(context),
    )


async def log_pipeline_broker_completed(context: PipelineContext, duration_ms: int) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_BROKER_COMPLETED,
        f"Broker complete: {context.symbol} {context.timeframe}",
        source="secretary",
        metadata=_base_metadata(context, duration_ms=duration_ms),
    )


async def log_pipeline_associate_started(context: PipelineContext, pair: str) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_ASSOCIATE_STARTED,
        f"Associate executing: {pair}",
        source="broker",
        metadata=_base_metadata(context, pair=pair),
    )


async def log_pipeline_associate_completed(context: PipelineContext, pair: str, duration_ms: int) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_ASSOCIATE_COMPLETED,
        f"Associate complete: {pair}",
        source="broker",
        metadata=_base_metadata(context, pair=pair, duration_ms=duration_ms),
    )


async def log_pipeline_failed(context: PipelineContext, step: str, error: str) -> None:
    await record_bot_activity(
        ACTION_PIPELINE_FAILED,
        f"Pipeline failed at {step}: {context.symbol} {context.timeframe}",
        detail=error,
        source="secretary",
        metadata=_base_metadata(context, step=step, error=error),
    )


async def log_account_summary_updated(asset_class: str, detail: str | None = None) -> None:
    await record_bot_activity(
        ACTION_ACCOUNT_SUMMARY_UPDATED,
        f"Account summary updated: {asset_class}",
        detail=detail,
        source="secretary",
        metadata={"asset_class": asset_class},
    )
