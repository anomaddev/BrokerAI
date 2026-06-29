from datetime import datetime, timezone

from brokerai.market_sessions import normalize_enabled_sessions
from brokerai.trading.execution_gates import passes_execution_gates
from brokerai.trading.session_gate import is_asset_trading_session_active
from brokerai.trading.types import AnalysisResult


def test_normalize_enabled_sessions_defaults_all_true():
    sessions = normalize_enabled_sessions(None)
    assert sessions == {"asia": True, "london": True, "ny": True}


def test_is_asset_trading_session_active_respects_enabled_sessions():
    # Wednesday 14:00 UTC — London and NY overlap
    when = datetime(2026, 3, 4, 14, 0, tzinfo=timezone.utc)
    assert is_asset_trading_session_active({"asia": False, "london": True, "ny": True}, when=when)
    assert not is_asset_trading_session_active({"asia": False, "london": False, "ny": False}, when=when)
    assert not is_asset_trading_session_active({"asia": True, "london": False, "ny": False}, when=when)


def test_is_asset_trading_session_active_blocks_weekend():
    when = datetime(2026, 3, 7, 14, 0, tzinfo=timezone.utc)  # Saturday
    assert not is_asset_trading_session_active({"asia": True, "london": True, "ny": True}, when=when)


def test_passes_execution_gates_blocks_asset_session():
    result = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.9,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
    )
    params = {
        "execution": {"min_confidence": 60, "sessions": ["London", "NY"]},
        "risk": {"max_trades_per_day": 3},
    }
    when = datetime(2026, 3, 4, 14, 0, tzinfo=timezone.utc)
    passed, reasons = passes_execution_gates(
        result,
        params,
        {},
        when=when,
        asset_enabled_sessions={"asia": False, "london": False, "ny": False},
    )
    assert passed is False
    assert "asset_session_inactive" in reasons
