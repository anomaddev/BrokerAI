from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.bots.executor.bot import ExecutorBot
from brokerai.trading.types import AnalysisResult


def _analysis(*, analyzed_at: datetime | None = None, pair: str = "EUR/USD") -> AnalysisResult:
    return AnalysisResult(
        strategy_id="strategy-1",
        strategy_name="Test",
        pair=pair,
        timeframe="M15",
        confidence=0.0,
        direction=None,
        min_candles=63,
        signal_type="hold",
        analyzed_at=analyzed_at or datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_executor_skips_already_processed_results():
    analyzer = MagicMock()
    analyzed_at = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)
    analyzer.get_recent_results.return_value = [_analysis(analyzed_at=analyzed_at)]

    bot = ExecutorBot()
    bot.attach_data_analyzer(analyzer)
    bot.attach_data_manager(AsyncMock())
    bot._processed_analysis_at[("strategy-1", "EUR/USD")] = analyzed_at

    with patch("brokerai.bots.executor.bot.load_runnable_forex_strategies", new_callable=AsyncMock):
        await bot.tick()

    analyzer.get_recent_results.assert_called_once()


@pytest.mark.asyncio
async def test_executor_processes_new_analysis_once():
    analyzer = MagicMock()
    first_at = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)
    analyzer.get_recent_results.return_value = [_analysis(analyzed_at=first_at)]

    bot = ExecutorBot()
    bot.attach_data_analyzer(analyzer)
    bot.attach_data_manager(AsyncMock())

    with (
        patch(
            "brokerai.bots.executor.bot.load_runnable_forex_strategies",
            new_callable=AsyncMock,
            return_value=MagicMock(strategies=[({"id": "strategy-1"}, ["EUR/USD"])]),
        ),
        patch(
            "brokerai.bots.executor.bot.TradesRepository",
            return_value=MagicMock(daily_trade_counts=AsyncMock(return_value={})),
        ),
        patch("brokerai.bots.executor.bot.passes_execution_gates", return_value=(False, ["no_signal"])),
    ):
        await bot.tick()

    assert bot._processed_analysis_at[("strategy-1", "EUR/USD")] == first_at

    with patch("brokerai.bots.executor.bot.load_runnable_forex_strategies", new_callable=AsyncMock):
        await bot.tick()

    assert analyzer.get_recent_results.call_count == 2
