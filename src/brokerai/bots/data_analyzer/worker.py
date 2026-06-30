from __future__ import annotations

import logging

from brokerai.bots.base import EphemeralBot, WorkerResult
from brokerai.bots.data_manager.candle_requirements import strategy_params
from brokerai.bots.data_manager.candles import OANDA_SOURCE
from brokerai.bots.data_manager.service import require_data_manager_service
from brokerai.bots.secretary.types import PipelineContext
from brokerai.core.pipeline_candle_cache import get_pipeline_candle_cache
from brokerai.db.repositories.strategy_analysis_runs import StrategyAnalysisRunsRepository
from brokerai.trading.candle_context import load_candles_for_unit
from brokerai.trading.indicator_cache import IndicatorCache
from brokerai.trading.pipeline import log_analysis_result, run_strategy_analysis
from brokerai.trading.types import AnalysisResult, WorkUnit

logger = logging.getLogger(__name__)

_indicator_cache = IndicatorCache()


class ForexDataAnalystWorker(EphemeralBot[PipelineContext, list[AnalysisResult]]):
    """On-demand strategy analysis worker for forex pipelines."""

    name = "forex_data_analyst_worker"
    asset_class = "forex"

    async def run(self, request: PipelineContext) -> WorkerResult[list[AnalysisResult]]:
        if not request.strategies:
            return WorkerResult(ok=True, data=[])

        service = require_data_manager_service()
        unit = WorkUnit(
            pair=request.symbol,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            bar_count=request.bar_count,
            strategies=request.strategies,
        )

        candles: list[dict] | None = None
        if request.candles_ref:
            candles = get_pipeline_candle_cache().get(request.candles_ref)

        if not candles:
            candles = await load_candles_for_unit(
                unit,
                service=service,
                requester="forex_data_analyst_worker",
            )

        if not candles:
            return WorkerResult(
                ok=False,
                error=f"No candles for {request.symbol} {request.timeframe}",
            )

        latest_time = request.latest_candle_time
        if not latest_time:
            latest_time = await service.latest_candle_time(
                request.symbol,
                request.timeframe,
                source=OANDA_SOURCE,
            )

        logger.info(
            "Data Analyst — analyzing %d strateg%s for %s %s through %s",
            len(unit.strategies),
            "y" if len(unit.strategies) == 1 else "ies",
            unit.pair,
            unit.timeframe,
            latest_time or "unknown",
        )

        cache = _indicator_cache.warm(
            unit.pair,
            unit.timeframe,
            candles,
            [strategy_params(strategy) for strategy in unit.strategies],
        )

        results: list[AnalysisResult] = []
        for strategy in unit.strategies:
            analysis = run_strategy_analysis(
                strategy,
                unit.pair,
                candles,
                cache,
                timeframe=unit.timeframe,
            )
            persisted = await StrategyAnalysisRunsRepository().insert_from_result(
                analysis,
                candle_time=latest_time,
            )
            analysis.run_id = persisted["id"]
            log_analysis_result(analysis)
            results.append(analysis)

        return WorkerResult(
            ok=True,
            data=results,
            metadata={"latest_candle_time": latest_time, "count": len(results)},
        )
