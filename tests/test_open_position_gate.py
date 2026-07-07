from datetime import datetime, timezone

from brokerai.trading.execution_gates import passes_execution_gates, passes_open_position_gate
from brokerai.trading.types import AnalysisResult


def test_passes_open_position_gate_blocks_when_enabled():
    assert passes_open_position_gate("EUR/USD", open_pairs={"EUR/USD"}, only_one_position_per_pair=True) is False
    assert passes_open_position_gate("EUR/USD", open_pairs={"GBP/USD"}, only_one_position_per_pair=True) is True
    assert passes_open_position_gate("EUR/USD", open_pairs={"EUR/USD"}, only_one_position_per_pair=False) is True
    assert passes_open_position_gate("EUR/USD", open_pairs=None, only_one_position_per_pair=True) is True


def test_passes_execution_gates_blocks_open_position():
    result = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.75,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
        metadata={"signal": "bullish_cross", "filters_passed": True},
    )
    passed, reasons, details = passes_execution_gates(
        result,
        {"execution": {"min_confidence": 0}, "risk": {"max_trades_per_day": 3}},
        {},
        when=datetime.now(timezone.utc),
        open_pairs={"EUR/USD"},
        only_one_position_per_pair=True,
    )
    assert passed is False
    assert "open_position_exists" in reasons
    assert details["open_position_exists"]["pair"] == "EUR/USD"


def test_passes_execution_gates_allows_entry_when_position_gate_disabled():
    result = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.75,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
        metadata={"signal": "bullish_cross", "filters_passed": True},
    )
    passed, reasons, _details = passes_execution_gates(
        result,
        {"execution": {"min_confidence": 0}, "risk": {"max_trades_per_day": 3}},
        {},
        when=datetime.now(timezone.utc),
        open_pairs={"EUR/USD"},
        only_one_position_per_pair=False,
    )
    assert passed is True
    assert "open_position_exists" not in reasons
