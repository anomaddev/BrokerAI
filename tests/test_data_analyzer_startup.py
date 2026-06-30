from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.bots.data_analyzer.bot import DataAnalyzerBot
from brokerai.trading.candle_revision import GLOBAL_CANDLE_REVISIONS
from brokerai.trading.types import AnalysisResult, WorkUnit


def _sample_unit() -> WorkUnit:
    return WorkUnit(
        pair="EUR/USD",
        asset_class="forex",
        timeframe="M15",
        bar_count=63,
        strategies=(
            {
                "id": "strategy-1",
                "name": "Test",
                "timeframe": "M15",
                "params": {"min_candles": 63},
            },
        ),
    )


def _mock_runtime(unit: WorkUnit) -> MagicMock:
    runtime = MagicMock()
    runtime.load_runnable_strategies = AsyncMock(
        return_value=MagicMock(
            skip_reason=None,
            strategies=[({"id": "strategy-1", "name": "Test", "timeframe": "M15"}, ["EUR/USD"])],
        )
    )
    runtime.build_work_plan.return_value = MagicMock(units=[unit])
    return runtime


@pytest.mark.asyncio
async def test_first_tick_analyzes_when_no_prior_revision():
    bot = DataAnalyzerBot()
    data_manager = AsyncMock()
    data_manager.latest_candle_time.return_value = "2026-01-01T00:15:00.000000000Z"
    data_manager.request_candles = AsyncMock(
        return_value=[
            {
                "time": "2026-01-01T00:15:00.000000000Z",
                "open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "close": 1.05,
                "volume": 0,
            }
        ]
    )
    bot.attach_data_manager(data_manager)
    unit = _sample_unit()

    with (
        patch("brokerai.bots.data_analyzer.bot.get_asset_runtime", return_value=_mock_runtime(unit)),
        patch("brokerai.bots.data_analyzer.bot.run_strategy_analysis") as run_analysis,
        patch(
            "brokerai.bots.data_analyzer.bot.StrategyAnalysisRunsRepository",
        ) as runs_repo_cls,
        patch.object(bot, "_sync_exit_monitors", new_callable=AsyncMock),
    ):
        runs_repo = AsyncMock()
        runs_repo.insert_from_result.return_value = {"id": "run-123"}
        runs_repo_cls.return_value = runs_repo
        analysis = AnalysisResult(
            strategy_id="strategy-1",
            strategy_name="Test",
            pair="EUR/USD",
            timeframe="M15",
            confidence=0.0,
            direction=None,
            min_candles=63,
            signal_type="hold",
        )
        run_analysis.return_value = analysis
        await bot.run_startup_pass()

    run_analysis.assert_called_once()
    runs_repo.insert_from_result.assert_awaited_once()
    assert analysis.run_id == "run-123"
    data_manager.request_candles.assert_awaited_once()
    assert data_manager.request_candles.await_args.kwargs["bar_count"] == 63


@pytest.mark.asyncio
async def test_second_tick_skips_without_new_candle():
    bot = DataAnalyzerBot()
    data_manager = AsyncMock()
    latest = "2026-01-01T00:15:00.000000000Z"
    data_manager.latest_candle_time.return_value = latest
    data_manager.request_candles = AsyncMock(return_value=[])
    bot.attach_data_manager(data_manager)
    GLOBAL_CANDLE_REVISIONS.mark_updated("EUR/USD", "M15", latest)
    unit = _sample_unit()

    with (
        patch("brokerai.bots.data_analyzer.bot.get_asset_runtime", return_value=_mock_runtime(unit)),
        patch("brokerai.bots.data_analyzer.bot.run_strategy_analysis") as run_analysis,
        patch.object(bot, "_sync_exit_monitors", new_callable=AsyncMock),
    ):
        await bot.tick()

    run_analysis.assert_not_called()
    data_manager.request_candles.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_analyzes_when_latest_candle_changes():
    bot = DataAnalyzerBot()
    data_manager = AsyncMock()
    data_manager.latest_candle_time.return_value = "2026-01-01T00:30:00.000000000Z"
    data_manager.request_candles = AsyncMock(
        return_value=[{"time": "2026-01-01T00:30:00.000000000Z", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 0}]
    )
    bot.attach_data_manager(data_manager)
    GLOBAL_CANDLE_REVISIONS.mark_updated("EUR/USD", "M15", "2026-01-01T00:15:00.000000000Z")
    unit = _sample_unit()

    with (
        patch("brokerai.bots.data_analyzer.bot.get_asset_runtime", return_value=_mock_runtime(unit)),
        patch("brokerai.bots.data_analyzer.bot.run_strategy_analysis") as run_analysis,
        patch.object(bot, "_sync_exit_monitors", new_callable=AsyncMock),
    ):
        run_analysis.return_value = AnalysisResult(
            strategy_id="strategy-1",
            strategy_name="Test",
            pair="EUR/USD",
            timeframe="M15",
            confidence=0.0,
            direction=None,
            min_candles=63,
            signal_type="hold",
        )
        await bot.tick()

    run_analysis.assert_called_once()
