from datetime import datetime, timezone

from brokerai.trading.execution_gates import (
    is_executor_eligible,
    passes_execution_gates,
    resolve_priority_conflicts,
)
from brokerai.trading.session_gate import normalize_strategy_session, normalize_strategy_sessions
from brokerai.trading.types import AnalysisResult


def test_normalize_strategy_session_aliases():
    assert normalize_strategy_session("London") == "london"
    assert normalize_strategy_session("Tokyo") == "asia"
    assert normalize_strategy_session("Singapore") == "asia"
    assert normalize_strategy_session("Hong Kong") == "asia"
    assert normalize_strategy_session("Asia") == "asia"
    assert normalize_strategy_session("Sydney") == "sydney"


def test_normalize_strategy_sessions_maps_legacy_names():
    assert normalize_strategy_sessions(["Tokyo", "Singapore"]) == ["asia"]
    assert normalize_strategy_sessions(["Asia"]) == ["asia"]


def test_is_executor_eligible_requires_signal_and_confidence():
    no_signal = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.0,
        direction=None,
        min_candles=50,
        signal_type="ema_crossover",
    )
    zero_confidence = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.0,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
    )
    actionable = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.75,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
    )

    assert is_executor_eligible(no_signal) is False
    assert is_executor_eligible(zero_confidence) is False
    assert is_executor_eligible(actionable) is True


def test_is_executor_eligible_when_filters_failed_but_signal_present():
    blocked = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.75,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
        metadata={"signal": "bullish_cross", "filters_passed": False},
    )
    assert is_executor_eligible(blocked) is True


def test_is_executor_eligible_rejects_approaching_signal():
    approaching = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.65,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
        metadata={"signal": "approaching_bullish_cross"},
    )
    assert is_executor_eligible(approaching) is False


def test_passes_execution_gates_blocks_failed_filters():
    result = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.75,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
        metadata={
            "signal": "bullish_cross",
            "filters_passed": False,
            "filters": {
                "adx": {
                    "passed": False,
                    "adx": 18.53,
                    "threshold": 25,
                    "compare": "gte",
                },
                "atr": {
                    "passed": False,
                    "atr": 0.0002,
                    "min_value": 0.0008,
                },
            },
        },
    )
    passed, reasons, details = passes_execution_gates(
        result,
        {"execution": {"min_confidence": 0}, "risk": {"max_trades_per_day": 3}},
        {},
        when=datetime.now(timezone.utc),
    )
    assert passed is False
    assert "filter_adx_failed" in reasons
    assert "filter_atr_failed" in reasons
    assert details["filter_adx_failed"]["adx"] == 18.53
    assert details["filter_atr_failed"]["min_value"] == 0.0008


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
    passed, reasons, details = passes_execution_gates(result, params, {}, when=datetime.now(timezone.utc))
    assert passed is False
    assert "confidence_below_threshold" in reasons
    assert details["confidence_below_threshold"]["confidence_pct"] == 50.0


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
