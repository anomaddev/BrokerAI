from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.bots.secretary.types import PipelineContext
from brokerai.trading.broker_execution import run_broker_execution
from brokerai.trading.types import AnalysisResult


def _strategy() -> dict:
    return {
        "id": "strategy-1",
        "name": "Test",
        "timeframe": "M15",
        "params": {"timeframe": "M15"},
    }


def _context(strategy: dict) -> PipelineContext:
    return PipelineContext(
        job_id="job-1",
        asset_class="forex",
        symbol="EUR/USD",
        timeframe="M15",
        trigger_time=datetime.now(timezone.utc),
        bar_count=50,
        strategies=(strategy,),
    )


def _ineligible_analysis() -> AnalysisResult:
    return AnalysisResult(
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
        metadata={"signal": "none"},
    )


def _mock_broker_deps(
    mock_load_strategies,
    mock_lots_cls,
    mock_asset_cls,
) -> None:
    strategy = _strategy()
    mock_load_strategies.return_value = type(
        "Loaded",
        (),
        {"strategies": [(strategy, ["EUR/USD"])]},
    )()
    mock_lots_cls.return_value.daily_lot_counts = AsyncMock(return_value={})
    mock_lots_cls.return_value.list_open_lots = AsyncMock(return_value=[])
    mock_asset_cls.return_value.get = AsyncMock(
        return_value={"enabled_sessions": {}, "only_one_position_per_pair": True}
    )


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
    mock_monitor_cls,
) -> None:
    _mock_broker_deps(mock_load_strategies, mock_lots_cls, mock_asset_cls)
    mock_monitor = MagicMock()
    mock_monitor.sync_exit_monitors = AsyncMock()
    mock_monitor_cls.return_value = mock_monitor

    analysis = _ineligible_analysis()
    context = _context(_strategy())

    intents = await run_broker_execution([analysis], context, data_manager=AsyncMock())

    assert intents == []
    mock_record_outcomes.assert_awaited_once()
    mock_monitor.sync_exit_monitors.assert_awaited_once()
    mock_apply_gates.assert_not_awaited()


@pytest.mark.asyncio
@patch("brokerai.trading.broker_execution.BrokerMonitor")
@patch("brokerai.trading.broker_execution.record_execution_outcomes", new_callable=AsyncMock)
@patch("brokerai.trading.broker_execution.apply_execution_gates", new_callable=AsyncMock)
@patch("brokerai.trading.broker_execution.AssetSettingsRepository")
@patch("brokerai.trading.broker_execution.BrokerLotsRepository")
@patch("brokerai.trading.broker_execution.load_runnable_forex_strategies")
async def test_run_broker_execution_evaluates_exits_without_entry_signal(
    mock_load_strategies,
    mock_lots_cls,
    mock_asset_cls,
    mock_apply_gates,
    mock_record_outcomes,
    mock_monitor_cls,
) -> None:
    """Reverse-crossover exits must run when entry analysis returns signal=none."""
    _mock_broker_deps(mock_load_strategies, mock_lots_cls, mock_asset_cls)
    mock_monitor = MagicMock()
    mock_monitor.sync_exit_monitors = AsyncMock()
    mock_monitor_cls.return_value = mock_monitor

    analysis = _ineligible_analysis()
    context = _context(_strategy())

    intents = await run_broker_execution([analysis], context, data_manager=AsyncMock())

    assert intents == []
    mock_record_outcomes.assert_awaited_once()
    mock_monitor.sync_exit_monitors.assert_awaited_once()
    sync_args, sync_kwargs = mock_monitor.sync_exit_monitors.await_args
    assert sync_kwargs["evaluate_pairs"] == {("EUR/USD", "M15")}
    mock_apply_gates.assert_not_awaited()
