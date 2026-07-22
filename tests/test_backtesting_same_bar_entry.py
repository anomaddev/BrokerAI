from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from brokerai.backtesting.actions import build_signal_actions
from brokerai.backtesting.engine import blocks_same_bar_entry, run_backtest_engine
from brokerai.backtesting.simulator import BacktestSimulator
from brokerai.db.repositories.backtest_actions import BacktestActionsRepository
from brokerai.db.repositories.backtest_runs import BacktestRunsRepository
from brokerai.strategies.presets.ema_crossover.definition import DEFAULT_PARAMS
from brokerai.trading.types import AnalysisResult
from tests.fixtures.mock_candles import generate_mock_candles

pytestmark = pytest.mark.usefixtures("sqlite_db")


def _iso_candles(count: int = 120) -> list[dict]:
    raw = generate_mock_candles(count)
    start = datetime(2025, 1, 6, 13, 0, tzinfo=timezone.utc)  # Monday
    out = []
    for index, candle in enumerate(raw):
        when = start + timedelta(minutes=15 * index)
        out.append(
            {
                **candle,
                "time": when.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
                "volume": float(candle.get("volume") or 0),
            }
        )
    return out


def test_blocks_same_bar_entry_only_for_signal_exits():
    assert blocks_same_bar_entry("reverse_crossover") is True
    assert blocks_same_bar_entry("REVERSE_CROSSOVER") is True
    assert blocks_same_bar_entry("stop_loss") is False
    assert blocks_same_bar_entry("take_profit") is False
    assert blocks_same_bar_entry("session_boundary") is False
    assert blocks_same_bar_entry(None) is False


def test_build_signal_actions_reports_closed_on_signal_skip():
    analysis = SimpleNamespace(
        direction="short",
        confidence=0.8,
        metadata={
            "signal": "bearish_crossover",
            "filters_passed": True,
            "filters": {},
        },
    )
    candle = {
        "time": "2025-01-06T14:00:00.000000000Z",
        "open": 1.1,
        "high": 1.11,
        "low": 1.09,
        "close": 1.1,
    }
    actions = build_signal_actions(
        analysis,
        candle,
        sequence_start=3,
        gate_passed=False,
        gate_reasons=["closed_on_signal"],
        gate_details={"closed_on_signal": {"exit_reason": "reverse_crossover"}},
    )
    assert len(actions) == 1
    assert actions[0]["kind"] == "signal"
    assert "skipped" in actions[0]["message"].lower()
    assert "closed prior position" in actions[0]["message"].lower()


@pytest.mark.asyncio
async def test_approaching_signal_does_not_open_position(monkeypatch):
    """Approaching crosses are watch-only live; backtests must not orphan-enter on them."""
    candles = _iso_candles(100)
    strategy = {
        "id": "strategy-bt-approach",
        "name": "EMA Approach",
        "asset_class": "forex",
        "timeframe": "M15",
        "instruments": ["EUR/USD"],
        "params": {
            **DEFAULT_PARAMS,
            "filters": [
                {**DEFAULT_PARAMS["filters"][0], "enabled": False},
                {**DEFAULT_PARAMS["filters"][1], "enabled": False},
            ],
            "execution": {
                **DEFAULT_PARAMS["execution"],
                "min_confidence": 0,
                "sessions": ["Sydney", "Asia", "London", "NY"],
            },
            "exits": {
                "stop_loss": {"enabled": False, "mode": "fixed_pips", "fixed_pips": 15},
                "take_profit": {"enabled": False, "mode": "fixed_pips", "fixed_pips": 30},
            },
        },
    }
    created = await BacktestRunsRepository().create_queued_runs(
        [strategy],
        instrument="EUR/USD",
        period="1m",
        period_start=candles[40]["time"],
        period_end=candles[-1]["time"],
    )
    run_id = created[0]["id"]
    raw = await BacktestRunsRepository().get_raw_doc(run_id)
    assert raw is not None

    async def approaching_only(strategy_doc, pair, window, indicators, **kwargs):
        _ = strategy_doc, window, indicators, kwargs
        return AnalysisResult(
            strategy_id="strategy-bt-approach",
            strategy_name="EMA Approach",
            pair=pair,
            timeframe="M15",
            confidence=0.85,
            direction="short",
            min_candles=50,
            signal_type="ema_crossover",
            metadata={
                "signal": "approaching_bearish_cross",
                "filters_passed": True,
                "filters": {},
            },
        )

    monkeypatch.setattr(
        "brokerai.backtesting.engine.run_strategy_analysis",
        approaching_only,
    )

    import logging

    result = await run_backtest_engine(
        raw,
        log=logging.getLogger("test.backtest.approach"),
        candles_override=candles,
    )
    assert result["status"] == "completed"

    actions = await BacktestActionsRepository().list_for_run(run_id, limit=5000)
    entries = [action for action in actions if action.get("kind") == "entry"]
    assert entries == [], "approaching signals must not open backtest positions"


@pytest.mark.asyncio
async def test_reverse_crossover_exit_does_not_open_same_bar(monkeypatch):
    """Closing on reverse_crossover must not flip into a new entry on that bar."""
    candles = _iso_candles(100)
    strategy = {
        "id": "strategy-bt-no-flip",
        "name": "EMA No Flip",
        "asset_class": "forex",
        "timeframe": "M15",
        "instruments": ["EUR/USD"],
        "params": {
            **DEFAULT_PARAMS,
            "filters": [
                {**DEFAULT_PARAMS["filters"][0], "enabled": False},
                {**DEFAULT_PARAMS["filters"][1], "enabled": False},
            ],
            "execution": {
                **DEFAULT_PARAMS["execution"],
                "min_confidence": 0,
                "sessions": ["Sydney", "Asia", "London", "NY"],
            },
            "exits": {
                "stop_loss": {"enabled": False, "mode": "fixed_pips", "fixed_pips": 15},
                "take_profit": {
                    "enabled": True,
                    "mode": "reverse_crossover",
                },
            },
        },
    }
    created = await BacktestRunsRepository().create_queued_runs(
        [strategy],
        instrument="EUR/USD",
        period="1m",
        period_start=candles[40]["time"],
        period_end=candles[-1]["time"],
    )
    run_id = created[0]["id"]
    raw = await BacktestRunsRepository().get_raw_doc(run_id)
    assert raw is not None

    async def force_reverse_exit(self, window, indicators):
        _ = indicators
        if not self.has_open_position() or not window:
            return None
        candle = window[-1]
        return self._close(
            price=float(candle["close"]),
            time=str(candle.get("time") or ""),
            reason="reverse_crossover",
        )

    async def always_long_signal(strategy_doc, pair, window, indicators, **kwargs):
        _ = strategy_doc, window, indicators, kwargs
        return AnalysisResult(
            strategy_id="strategy-bt-no-flip",
            strategy_name="EMA No Flip",
            pair=pair,
            timeframe="M15",
            confidence=0.9,
            direction="long",
            min_candles=50,
            signal_type="ema_crossover",
            metadata={
                "signal": "bullish_crossover",
                "filters_passed": True,
                "filters": {},
            },
        )

    monkeypatch.setattr(BacktestSimulator, "check_exit_monitors", force_reverse_exit)
    monkeypatch.setattr(
        "brokerai.backtesting.engine.run_strategy_analysis",
        always_long_signal,
    )

    import logging

    result = await run_backtest_engine(
        raw,
        log=logging.getLogger("test.backtest.no_flip"),
        candles_override=candles,
    )
    assert result["status"] == "completed"

    actions = await BacktestActionsRepository().list_for_run(run_id, limit=5000)
    exits = [a for a in actions if a.get("kind") == "exit"]
    assert exits, "expected at least one reverse-crossover exit"

    for exit_action in exits:
        if (exit_action.get("meta") or {}).get("reason") != "reverse_crossover":
            continue
        bar_time = exit_action.get("bar_time")
        seq = int(exit_action["sequence"])
        same_bar_entries = [
            a
            for a in actions
            if a.get("kind") == "entry"
            and a.get("bar_time") == bar_time
            and int(a["sequence"]) > seq
        ]
        assert same_bar_entries == [], (
            f"entry must not follow reverse_crossover exit on the same bar ({bar_time})"
        )
