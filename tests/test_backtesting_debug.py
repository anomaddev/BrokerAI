from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import pytest

from brokerai.backtesting.debug import (
    BacktestBarSnapshot,
    InteractiveBacktestDebugger,
    StepAction,
    parse_break_on,
    run_backtest,
)
from brokerai.backtesting.engine import run_backtest_engine
from brokerai.db.repositories.backtest_runs import BacktestRunsRepository
from brokerai.strategies.presets.ema_crossover.definition import DEFAULT_PARAMS
from brokerai.trading.types import AnalysisResult
from tests.fixtures.mock_candles import generate_mock_candles

pytestmark = pytest.mark.usefixtures("sqlite_db")


def _iso_candles(count: int = 200) -> list[dict]:
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


def _strategy(strategy_id: str = "strategy-debug") -> dict:
    return {
        "id": strategy_id,
        "name": "EMA Debug",
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
                "sessions": ["Sydney", "Asia", "London", "NY"],
            },
        },
    }


def _snapshot(**overrides) -> BacktestBarSnapshot:
    analysis = AnalysisResult(
        strategy_id="s",
        strategy_name="S",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.8,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
        metadata={"signal": "bullish_crossover", "filters_passed": True},
    )
    base = dict(
        bar_index=10,
        period_start_idx=5,
        bars_done=6,
        total_bars=100,
        bar_time="2025-01-06T15:00:00.000000000Z",
        candle={"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "time": "2025-01-06T15:00:00.000000000Z"},
        analysis=analysis,
        gate_passed=True,
        gate_reasons=[],
        gate_details={},
        closed_trade=None,
        position=None,
        actions=[{"kind": "signal", "sequence": 0, "message": "Crossover"}],
        equity=10_000.0,
        closed_trade_count=0,
    )
    base.update(overrides)
    return BacktestBarSnapshot(**base)


def test_parse_break_on_defaults_and_rejects_unknown():
    assert parse_break_on(None) == ("action",)
    assert parse_break_on("signal, entry, SIGNAL") == ("signal", "entry")
    with pytest.raises(ValueError, match="Unknown"):
        parse_break_on("signal,nope")


def test_snapshot_matches_break_kinds():
    snap = _snapshot()
    assert snap.matches_break(("action",))
    assert snap.matches_break(("signal",))
    assert not snap.matches_break(("entry",))
    quiet = _snapshot(actions=[], analysis=AnalysisResult(
        strategy_id="s",
        strategy_name="S",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.0,
        direction=None,
        min_candles=50,
        signal_type="ema_crossover",
        metadata={"signal": "none"},
    ))
    assert not quiet.matches_break(("action", "signal"))
    assert quiet.matches_break(("bar",))


@pytest.mark.asyncio
async def test_interactive_debugger_continue_and_quit():
    out = io.StringIO()
    dbg = InteractiveBacktestDebugger(
        break_on=("action",),
        input_stream=io.StringIO("analysis\nn\nq\n"),
        output_stream=out,
    )
    first = await dbg(_snapshot())
    assert first == StepAction.CONTINUE
    second = await dbg(_snapshot(bar_time="2025-01-06T15:15:00.000000000Z"))
    assert second == StepAction.CANCEL
    text = out.getvalue()
    assert "direction=long" in text
    assert "Cancelling" in text


@pytest.mark.asyncio
async def test_interactive_debugger_until_skips_early_breaks():
    out = io.StringIO()
    dbg = InteractiveBacktestDebugger(
        break_on=("action",),
        until="2025-01-06T16:00:00.000000000Z",
        input_stream=io.StringIO("c\n"),
        output_stream=out,
    )
    early = await dbg(_snapshot(bar_time="2025-01-06T15:00:00.000000000Z"))
    assert early == StepAction.CONTINUE
    assert "break" not in out.getvalue()
    late = await dbg(_snapshot(bar_time="2025-01-06T16:00:00.000000000Z"))
    assert late == StepAction.CONTINUE
    assert "— break —" in out.getvalue()


@pytest.mark.asyncio
async def test_engine_on_bar_hook_receives_snapshots_and_can_cancel():
    import logging

    candles = _iso_candles(180)
    created = await BacktestRunsRepository().create_queued_runs(
        [_strategy("strategy-hook")],
        instrument="EUR/USD",
        period="1m",
        period_start=candles[40]["time"],
        period_end=candles[-1]["time"],
    )
    run_id = created[0]["id"]
    raw = await BacktestRunsRepository().get_raw_doc(run_id)
    assert raw is not None

    seen: list[str] = []

    async def on_bar(snap: BacktestBarSnapshot):
        seen.append(snap.bar_time)
        if len(seen) >= 3:
            return StepAction.CANCEL
        return StepAction.CONTINUE

    result = await run_backtest_engine(
        raw,
        log=logging.getLogger("test.backtest.hook"),
        candles_override=candles,
        on_bar=on_bar,
    )
    assert result["status"] == "cancelled"
    assert len(seen) == 3


@pytest.mark.asyncio
async def test_run_backtest_python_api_with_override_and_hook():
    candles = _iso_candles(180)
    snaps: list[BacktestBarSnapshot] = []

    async def on_bar(snap: BacktestBarSnapshot):
        snaps.append(snap)

    result = await run_backtest(
        strategy=_strategy("strategy-api"),
        instrument="EUR/USD",
        period="1m",
        candles_override=candles,
        on_bar=on_bar,
    )
    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["run_id"]
    assert snaps
    assert snaps[0].bars_done == 1
    finished = await BacktestRunsRepository().get_by_id(result["run_id"])
    assert finished is not None
    assert finished["status"] == "completed"


@pytest.mark.asyncio
async def test_run_backtest_interactive_eof_continues():
    candles = _iso_candles(120)
    out = io.StringIO()
    # Break on every bar; first prompt gets EOF → continue without pauses.
    result = await run_backtest(
        strategy=_strategy("strategy-eof"),
        instrument="EUR/USD",
        period="1m",
        candles_override=candles,
        interactive=True,
        break_on=("bar",),
        input_stream=io.StringIO(""),
        output_stream=out,
    )
    assert result["ok"] is True
    assert result["status"] == "completed"
    assert "EOF" in out.getvalue()
