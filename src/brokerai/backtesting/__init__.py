"""Strategy backtesting engine and coordinator."""

from __future__ import annotations

__all__ = [
    "BacktestBarSnapshot",
    "BacktestCoordinator",
    "InteractiveBacktestDebugger",
    "get_backtest_coordinator",
    "run_backtest",
    "run_backtest_engine",
]


def __getattr__(name: str):
    if name in {"BacktestCoordinator", "get_backtest_coordinator"}:
        from brokerai.backtesting.coordinator import BacktestCoordinator, get_backtest_coordinator

        return {
            "BacktestCoordinator": BacktestCoordinator,
            "get_backtest_coordinator": get_backtest_coordinator,
        }[name]
    if name == "run_backtest_engine":
        from brokerai.backtesting.engine import run_backtest_engine

        return run_backtest_engine
    if name in {
        "BacktestBarSnapshot",
        "InteractiveBacktestDebugger",
        "run_backtest",
    }:
        from brokerai.backtesting import debug as debug_mod

        return getattr(debug_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
