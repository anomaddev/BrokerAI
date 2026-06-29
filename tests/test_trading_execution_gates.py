from datetime import datetime, timezone

from brokerai.trading.execution_gates import passes_execution_gates, resolve_priority_conflicts
from brokerai.trading.session_gate import normalize_strategy_session
from brokerai.trading.types import AnalysisResult


def test_normalize_strategy_session_aliases():
    assert normalize_strategy_session("London") == "london"
    assert normalize_strategy_session("Sydney") == "asia"


def test_passes_execution_gates_blocks_low_confidence():
    result = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.5,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
    )
    params = {
        "execution": {"min_confidence": 60, "sessions": ["London"]},
        "risk": {"max_trades_per_day": 3},
    }
    passed, reasons = passes_execution_gates(result, params, {}, when=datetime.now(timezone.utc))
    assert passed is False
    assert "confidence_below_threshold" in reasons


def test_resolve_priority_conflicts_picks_lower_priority_value():
    high = AnalysisResult(
        strategy_id="high",
        strategy_name="High",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.9,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
    )
    low = AnalysisResult(
        strategy_id="low",
        strategy_name="Low",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.8,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
    )
    winners = resolve_priority_conflicts(
        [
            (high, {"execution": {"priority": 80, "override_all_strategies": False}}),
            (low, {"execution": {"priority": 10, "override_all_strategies": False}}),
        ]
    )
    assert len(winners) == 1
    assert winners[0][0].strategy_id == "low"
