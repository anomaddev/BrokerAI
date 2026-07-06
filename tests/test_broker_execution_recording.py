from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.bots.secretary.types import PipelineContext
from brokerai.trading.broker_execution import run_broker_execution
from brokerai.trading.types import AnalysisResult


@pytest.mark.asyncio
@patch("brokerai.trading.broker_execution.BrokerMonitor")
@patch("brokerai.trading.broker_execution.record_execution_outcomes", new_callable=AsyncMock)
@patch("brokerai.trading.broker_execution.apply_execution_gates", new_callable=AsyncMock)
@patch("brokerai.trading.broker_execution.AssetSettingsRepository")
@patch("brokerai.trading.broker_execution.BrokerLotsRepository")
@patch("brokerai.trading.broker_execution.load_runnable_forex_strategies")
async def test_run_broker_execution_records_ineligible_outcomes(
    mock_load_strategies,
    mock_lots_cls,
    mock_asset_cls,
    mock_apply_gates,
    mock_record_outcomes,
    _mock_monitor_cls,
) -> None:
    strategy = {
        "id": "strategy-1",
        "name": "Test",
        "timeframe": "M15",
        "params": {"timeframe": "M15"},
    }
    mock_load_strategies.return_value = type(
        "Loaded",
        (),
        {"strategies": [(strategy, ["EUR/USD"])]},
    )()
    mock_lots_cls.return_value.daily_lot_counts = AsyncMock(return_value={})
    mock_asset_cls.return_value.get = AsyncMock(return_value={"enabled_sessions": {}})

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
    context = PipelineContext(
        job_id="job-1",
        asset_class="forex",
        symbol="EUR/USD",
        timeframe="M15",
        trigger_time=datetime.now(timezone.utc),
        bar_count=50,
        strategies=(strategy,),
    )

    intents = await run_broker_execution([analysis], context, data_manager=AsyncMock())

    assert intents == []
    mock_record_outcomes.assert_awaited_once()
    mock_apply_gates.assert_not_awaited()
