from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.manual_analysis import run_manual_strategy_analysis
from brokerai.trading.types import AnalysisResult


@pytest.mark.asyncio
@patch("brokerai.trading.broker_execution.dispatch_trade_intents", new_callable=AsyncMock)
@patch("brokerai.trading.broker_execution.run_broker_execution", new_callable=AsyncMock)
@patch("brokerai.bots.data_analyzer.assets.run_asset_analyst")
@patch("brokerai.trading.manual_analysis.StrategiesRepository")
@patch("brokerai.trading.manual_analysis.StrategyAnalysisRunsRepository")
async def test_manual_analysis_runs_broker_execution(
    mock_repo_cls,
    mock_strategies_cls,
    mock_run_analyst,
    mock_run_broker_execution,
    mock_dispatch_intents,
) -> None:
    strategy = {
        "id": "strategy-1",
        "name": "Test",
        "asset_class": "forex",
        "instruments": ["EUR/USD"],
        "timeframe": "M15",
        "params": {"timeframe": "M15"},
    }
    strategies_repo = AsyncMock()
    mock_strategies_cls.return_value = strategies_repo
    strategies_repo.get_by_id.return_value = strategy

    analysis = AnalysisResult(
        strategy_id="strategy-1",
        strategy_name="Test",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.0,
        direction=None,
        min_candles=50,
        signal_type="ema_crossover",
        analyzed_at=datetime.now(timezone.utc),
        run_id="run-1",
    )

    async def _run_analyst(_context):
        from brokerai.bots.base import WorkerResult

        return WorkerResult(ok=True, data=[analysis])

    mock_run_analyst.side_effect = _run_analyst

    runs_repo = AsyncMock()
    mock_repo_cls.return_value = runs_repo
    runs_repo.set_run_type.return_value = True
    runs_repo.get_by_id.return_value = {
        "id": "run-1",
        "strategy_id": "strategy-1",
        "strategy_name": "Test",
        "pair": "EUR/USD",
        "timeframe": "M15",
        "direction": None,
        "confidence": 0.0,
        "signal_type": "ema_crossover",
        "min_candles": 50,
        "metadata": {},
        "candle_time": None,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "run_type": "manual",
        "execution": None,
    }
    mock_run_broker_execution.return_value = []

    await run_manual_strategy_analysis(
        strategy_id="strategy-1",
        asset_class="forex",
        symbol="EUR/USD",
    )

    mock_run_broker_execution.assert_awaited_once()
    mock_dispatch_intents.assert_awaited_once()
    dispatch_kwargs = mock_dispatch_intents.await_args.kwargs
    assert dispatch_kwargs["job_id"] is not None
