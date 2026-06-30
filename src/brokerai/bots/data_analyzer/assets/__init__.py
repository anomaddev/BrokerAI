from __future__ import annotations

import logging

from brokerai.bots.base import WorkerResult
from brokerai.bots.secretary.types import PipelineContext
from brokerai.trading.types import AnalysisResult

logger = logging.getLogger(__name__)

_ASSET_CLASSES = ("stocks", "options", "futures", "metals", "crypto")


async def stub_analyze(
    context: PipelineContext,
    asset_class: str,
) -> WorkerResult[list[AnalysisResult]]:
    # TODO(loop): implement {asset_class} data analyst
    logger.info(
        "TODO(loop): implement %s data analyst for %s %s",
        asset_class,
        context.symbol,
        context.timeframe,
    )
    return WorkerResult(ok=True, data=[], metadata={"skipped": True})


async def run_asset_analyst(context: PipelineContext) -> WorkerResult[list[AnalysisResult]]:
    if context.asset_class == "forex":
        from brokerai.bots.data_analyzer.worker import ForexDataAnalystWorker

        worker = ForexDataAnalystWorker()
        await worker.start()
        try:
            return await worker.run(context)
        finally:
            await worker.stop()
    return await stub_analyze(context, context.asset_class)
