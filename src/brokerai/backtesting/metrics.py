"""Aggregate performance metrics from simulated backtest trades."""

from __future__ import annotations

from typing import Any


def compute_stats(
    trades: list[dict[str, Any]],
    *,
    equity_curve: list[dict[str, Any]] | None = None,
    initial_equity: float = 10_000.0,
) -> dict[str, Any]:
    """Compute total_trades, win_rate, realized_pnl, max_drawdown.

    ``max_drawdown`` is a fraction of peak equity (0.1 = 10% drawdown), or ``None``
    when there is no equity history and no closed trades.
    """
    closed = [t for t in trades if t.get("status") == "closed"]
    total = len(closed)
    realized = sum(float(t.get("realized_pnl") or 0.0) for t in closed)
    winners = sum(1 for t in closed if float(t.get("realized_pnl") or 0.0) > 0)
    win_rate = (winners / total) if total else None

    max_dd: float | None = None
    if equity_curve:
        peak = float(equity_curve[0].get("equity", initial_equity))
        worst = 0.0
        for point in equity_curve:
            equity = float(point.get("equity", initial_equity))
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = (peak - equity) / peak
                if dd > worst:
                    worst = dd
        max_dd = worst
    elif closed:
        equity = initial_equity
        peak = initial_equity
        worst = 0.0
        for trade in closed:
            equity += float(trade.get("realized_pnl") or 0.0)
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = (peak - equity) / peak
                if dd > worst:
                    worst = dd
        max_dd = worst

    return {
        "total_trades": total if total else 0,
        "win_rate": win_rate,
        "realized_pnl": realized,
        "max_drawdown": max_dd,
    }


def downsample_equity_curve(
    curve: list[dict[str, Any]],
    *,
    max_points: int = 500,
) -> list[dict[str, Any]]:
    """Downsample an equity curve for storage/UI (keeps first/last points)."""
    if len(curve) <= max_points:
        return list(curve)
    if max_points < 2:
        return [curve[-1]]
    step = (len(curve) - 1) / (max_points - 1)
    indexes = {int(round(i * step)) for i in range(max_points)}
    indexes.add(0)
    indexes.add(len(curve) - 1)
    return [curve[i] for i in sorted(indexes)]
