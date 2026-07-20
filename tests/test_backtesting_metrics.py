from __future__ import annotations

from brokerai.backtesting.metrics import compute_stats, downsample_equity_curve


def test_compute_stats_from_trades():
    trades = [
        {"status": "closed", "realized_pnl": 10.0},
        {"status": "closed", "realized_pnl": -5.0},
        {"status": "open", "realized_pnl": 0.0},
    ]
    stats = compute_stats(trades)
    assert stats["total_trades"] == 2
    assert stats["win_rate"] == 0.5
    assert stats["realized_pnl"] == 5.0
    assert stats["max_drawdown"] is not None


def test_downsample_equity_curve_keeps_ends():
    curve = [{"time": str(i), "equity": float(i)} for i in range(1000)]
    out = downsample_equity_curve(curve, max_points=10)
    assert len(out) == 10
    assert out[0]["time"] == "0"
    assert out[-1]["time"] == "999"
