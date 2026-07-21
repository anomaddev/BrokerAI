from __future__ import annotations

import logging

from brokerai.bots.base import EphemeralBot, WorkerResult
from brokerai.bots.data_manager.candle_requirements import htf_required_bars, strategy_params
from brokerai.bots.data_manager.candles import OANDA_SOURCE
from brokerai.bots.data_manager.service import require_data_manager_service
from brokerai.bots.secretary.types import PipelineContext
from brokerai.db.repositories.strategy_analysis_runs import StrategyAnalysisRunsRepository
from brokerai.trading.candle_context import fetch_live_candles_for_unit
from brokerai.trading.indicator_cache import IndicatorCache
from brokerai.trading.pipeline import log_analysis_result, run_strategy_analysis
from brokerai.trading.presets.ema_crossover.htf_bias import (
    attach_htf_ema_series,
    htf_bias_filter_spec,
    signal_ema_periods,
)
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

        try:
            candles = await fetch_live_candles_for_unit(unit, service=service)
        except ValueError as exc:
            return WorkerResult(ok=False, error=str(exc))

        if not candles:
            return WorkerResult(
                ok=False,
                error=f"No candles from OANDA for {request.symbol} {request.timeframe}",
            )

        latest_time = str(candles[-1].get("time") or "") or request.latest_candle_time

        logger.info(
            "Data Analyst — analyzing %d strateg%s for %s %s through %s",
            len(unit.strategies),
            "y" if len(unit.strategies) == 1 else "ies",
            unit.pair,
            unit.timeframe,
            latest_time or "unknown",
        )

        strategy_params_list = [strategy_params(strategy) for strategy in unit.strategies]
        cache = _indicator_cache.warm(
            unit.pair,
            unit.timeframe,
            candles,
            strategy_params_list,
        )

        # Warm higher-timeframe EMA series for enabled htf_bias filters (live parity).
        warmed_htf: set[str] = set()
        for params in strategy_params_list:
            spec = htf_bias_filter_spec(params)
            if spec is None:
                continue
            htf_tf = str(spec.get("timeframe") or "H4")
            if htf_tf in warmed_htf:
                continue
            bar_count = max(htf_required_bars(params), unit.bar_count, 120)
            try:
                htf_candles = await service.request_candles(
                    unit.pair,
                    htf_tf,
                    bar_count=bar_count,
                    source=OANDA_SOURCE,
                    requester="data_analyzer",
                )
                if not htf_candles:
                    htf_candles = await service.fetch_live_candles_from_oanda(
                        unit.pair,
                        htf_tf,
                        bar_count,
                    )
                fast_p, slow_p = signal_ema_periods(params)
                attach_htf_ema_series(
                    cache,
                    timeframe=htf_tf,
                    candles=htf_candles,
                    fast_period=fast_p,
                    slow_period=slow_p,
                )
                warmed_htf.add(htf_tf)
            except Exception:
                logger.warning(
                    "Data Analyst — failed to warm HTF bias candles for %s %s",
                    unit.pair,
                    htf_tf,
                    exc_info=True,
                )

        results: list[AnalysisResult] = []
        for strategy in unit.strategies:
            analysis = run_strategy_analysis(
                strategy,
                unit.pair,
                candles,
                cache,
                timeframe=unit.timeframe,
                catchup=request.catchup,
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
