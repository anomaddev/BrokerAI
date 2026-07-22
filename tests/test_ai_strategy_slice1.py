"""Tests for AI Strategy Slice 1 foundations."""

from __future__ import annotations

import pytest

from brokerai.ai_strategy.lifecycle import (
    PHASE_LIVE,
    PHASE_READY,
    PHASE_WARMING,
    advance_warmup_on_realtime_bar,
    ensure_lifecycle_on_create,
    get_execution_phase,
    promote_to_live,
)
from brokerai.ai_strategy.shadow_dispatch import (
    refuse_non_live_placement,
    strategy_allows_live_dispatch,
)
from brokerai.strategies.params import prepare_params
from brokerai.strategies.registry import get_preset, list_presets
from brokerai.trading.pipeline import ensure_trading_registries, run_strategy_analysis
from brokerai.trading.registries.signals import get_signal_evaluator
from brokerai.trading.indicator_cache import IndicatorCache


def test_ai_strategy_preset_registered():
    ids = {p.id for p in list_presets()}
    assert "ai_strategy" in ids
    preset = get_preset("ai_strategy")
    assert preset is not None
    assert preset.asset_classes == ["forex"]
    assert preset.signal_type == "ai_strategy"


def test_ai_params_round_trip():
    preset = get_preset("ai_strategy")
    assert preset is not None
    params = prepare_params(
        preset,
        {
            "schema_version": 1,
            "timeframe": "H1",
            "ai": {
                "llm_mode": "off",
                "use_daily_report": True,
                "use_weekly_brief": False,
                "max_llm_calls_per_day": 6,
            },
        },
    )
    assert params["signal"]["type"] == "ai_strategy"
    assert params["ai"]["llm_mode"] == "off"
    assert params["ai"]["use_weekly_brief"] is False
    assert params["ai"]["max_llm_calls_per_day"] == 6
    assert "ai" in params


def test_stub_evaluator_never_trades_and_no_llm():
    ensure_trading_registries()
    evaluator = get_signal_evaluator("ai_strategy")
    assert evaluator is not None
    preset = get_preset("ai_strategy")
    assert preset is not None
    params = prepare_params(preset, {"schema_version": 1, "timeframe": "M15"})
    cache = IndicatorCache().warm("EUR/USD", "M15", [], [params])
    result = evaluator.evaluate([], params, cache)
    assert result.direction is None
    assert result.confidence == 0.0
    assert result.metadata.get("llm_called") is False
    assert result.metadata.get("stub") is True

    analysis = run_strategy_analysis(
        {"id": "s1", "name": "AI", "params": params, "preset_id": "ai_strategy"},
        "EUR/USD",
        [],
        cache,
        timeframe="M15",
    )
    assert analysis.direction is None
    assert analysis.confidence == 0.0


def test_lifecycle_warmup_and_promote():
    doc = {
        "id": "x",
        "preset_id": "ai_strategy",
        "name": "AI",
        "asset_class": "forex",
    }
    doc = ensure_lifecycle_on_create(doc, default_warmup_trading_days=2)
    assert get_execution_phase(doc) == PHASE_WARMING
    assert strategy_allows_live_dispatch(doc) is False
    assert refuse_non_live_placement(doc)

    from datetime import datetime, timezone

    day1 = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    doc = advance_warmup_on_realtime_bar(
        doc, candle_time=day1, catchup=False, global_default_days=2, forex_open=True
    )
    assert get_execution_phase(doc) == PHASE_WARMING
    # Catchup must not advance
    before = doc["warmup"]["completed_days"]
    doc = advance_warmup_on_realtime_bar(
        doc, candle_time=day2, catchup=True, global_default_days=2, forex_open=True
    )
    assert doc["warmup"]["completed_days"] == before

    doc = advance_warmup_on_realtime_bar(
        doc, candle_time=day2, catchup=False, global_default_days=2, forex_open=True
    )
    assert get_execution_phase(doc) == PHASE_READY

    with pytest.raises(ValueError):
        promote_to_live({**doc, "execution_phase": PHASE_WARMING, "warmup": doc["warmup"]})

    live = promote_to_live(doc)
    assert get_execution_phase(live) == PHASE_LIVE
    assert strategy_allows_live_dispatch(live) is True
    assert refuse_non_live_placement(live) is None


def test_priority_prefers_live_over_warming_ai():
    from brokerai.trading.execution_gates import resolve_priority_conflicts
    from brokerai.trading.types import AnalysisResult
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    ai = AnalysisResult(
        strategy_id="ai1",
        strategy_name="AI",
        pair="EUR/USD",
        timeframe="M15",
        confidence=90.0,
        direction="long",
        min_candles=50,
        signal_type="ai_strategy",
        analyzed_at=now,
    )
    ema = AnalysisResult(
        strategy_id="ema1",
        strategy_name="EMA",
        pair="EUR/USD",
        timeframe="M15",
        confidence=70.0,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
        analyzed_at=now,
    )
    strategies = {
        "ai1": {
            "id": "ai1",
            "preset_id": "ai_strategy",
            "execution_phase": PHASE_WARMING,
            "params": {"execution": {"priority": 10}},
        },
        "ema1": {
            "id": "ema1",
            "preset_id": "ema_crossover",
            "params": {"execution": {"priority": 50}},
        },
    }
    winners = resolve_priority_conflicts(
        [
            (ai, strategies["ai1"]["params"]),
            (ema, strategies["ema1"]["params"]),
        ],
        strategies_by_id=strategies,
    )
    assert len(winners) == 1
    assert winners[0][0].strategy_id == "ema1"
