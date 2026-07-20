"""Strategy backtesting engine and coordinator."""

from __future__ import annotations

__all__ = ["BacktestCoordinator", "get_backtest_coordinator"]


def __getattr__(name: str):
    if name in {"BacktestCoordinator", "get_backtest_coordinator"}:
        from brokerai.backtesting.coordinator import BacktestCoordinator, get_backtest_coordinator

        return {
            "BacktestCoordinator": BacktestCoordinator,
            "get_backtest_coordinator": get_backtest_coordinator,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
