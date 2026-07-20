from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from brokerai.backtesting.engine import _sort_candles_oldest_first, run_backtest_engine
from brokerai.db.repositories.backtest_actions import BacktestActionsRepository
from brokerai.db.repositories.backtest_runs import BacktestRunsRepository
from brokerai.strategies.presets.ema_crossover.definition import DEFAULT_PARAMS
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


def test_sort_candles_oldest_first_reorders_reversed_series():
    candles = _iso_candles(5)
    reversed_candles = list(reversed(candles))
    assert reversed_candles[0]["time"] > reversed_candles[-1]["time"]
    ordered = _sort_candles_oldest_first(reversed_candles)
    assert [c["time"] for c in ordered] == [c["time"] for c in candles]


@pytest.mark.asyncio
async def test_run_backtest_engine_completes_with_overrides(caplog):
    import logging

    candles = _iso_candles(180)
    strategy = {
        "id": "strategy-bt",
        "name": "EMA BT",
        "asset_class": "forex",
        "timeframe": "M15",
        "instruments": ["EUR/USD"],
        "params": {
            **DEFAULT_PARAMS,
            "filters": [
                {**DEFAULT_PARAMS["filters"][0], "enabled": False},
                {**DEFAULT_PARAMS["filters"][1], "enabled": False},
            ],
            "execution": {**DEFAULT_PARAMS["execution"], "sessions": ["Sydney", "Asia", "London", "NY"]},
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

    log = logging.getLogger("test.backtest")
    result = await run_backtest_engine(
        raw,
        log=log,
        candles_override=candles,
    )
    assert result["status"] == "completed"
    assert "stats" in result
    finished = await BacktestRunsRepository().get_by_id(run_id)
    # Engine updates progress; finish_run is called by worker — here we only ran engine.
    assert finished is not None
    assert result["stats"]["total_trades"] is not None


@pytest.mark.asyncio
async def test_run_backtest_engine_walks_reversed_candles_oldest_to_newest():
    """Feeding newest-first candles must still simulate oldest → newest."""
    candles = _iso_candles(180)
    strategy = {
        "id": "strategy-bt-order",
        "name": "EMA Order",
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

    import logging

    result = await run_backtest_engine(
        raw,
        log=logging.getLogger("test.backtest.order"),
        candles_override=list(reversed(candles)),
    )
    assert result["status"] == "completed"

    actions = await BacktestActionsRepository().list_for_run(run_id, limit=5000)
    timed = [action for action in actions if action.get("bar_time")]
    assert timed, "expected recorded actions with bar times"
    times = [str(action["bar_time"]) for action in timed]
    assert times == sorted(times), "action bar times must advance oldest → newest"
