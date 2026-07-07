from brokerai.trading.exit_analysis import build_exit_analysis_result
from brokerai.trading.types import ExitIntent


def test_build_exit_analysis_result_no_signal():
    trade = {
        "id": "lot-1",
        "strategy_id": "s1",
        "strategy_name": "EMA",
        "pair": "EUR/USD",
        "direction": "long",
        "exit_mode": "reverse_crossover",
    }
    strategy = {"id": "s1", "name": "EMA"}
    result = build_exit_analysis_result(
        trade,
        strategy,
        timeframe="M15",
        exit_intent=None,
    )
    assert result.metadata["analysis_purpose"] == "exit"
    assert result.metadata["exit_triggered"] is False
    assert result.direction is None
    assert result.confidence == 0.0


def test_build_exit_analysis_result_reverse_cross():
    trade = {
        "id": "lot-1",
        "strategy_id": "s1",
        "strategy_name": "EMA",
        "pair": "EUR/USD",
        "direction": "long",
        "exit_mode": "reverse_crossover",
    }
    strategy = {"id": "s1", "name": "EMA"}
    exit_intent = ExitIntent(
        trade_id="lot-1",
        strategy_id="s1",
        pair="EUR/USD",
        reason="reverse_crossover",
        metadata={"signal": "bearish_cross", "confidence": 0.82},
    )
    result = build_exit_analysis_result(
        trade,
        strategy,
        timeframe="M15",
        exit_intent=exit_intent,
        signal_metadata=exit_intent.metadata,
    )
    assert result.metadata["exit_triggered"] is True
    assert result.metadata["exit_reason"] == "reverse_crossover"
    assert result.direction == "short"
    assert result.confidence == 0.82
