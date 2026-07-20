from __future__ import annotations

from datetime import datetime, timezone

from brokerai.backtesting.periods import format_oanda_bound, resolve_period_window


def test_resolve_period_window_six_months():
    end = datetime(2026, 7, 19, 16, 0, tzinfo=timezone.utc)
    start, resolved_end = resolve_period_window("6m", end=end)
    assert resolved_end == end
    assert start < end
    assert (end - start).days >= 180


def test_resolve_period_window_unknown_falls_back_to_six_months():
    end = datetime(2026, 1, 1, tzinfo=timezone.utc)
    start_a, _ = resolve_period_window("6m", end=end)
    start_b, _ = resolve_period_window("not-a-period", end=end)
    assert start_a == start_b


def test_format_oanda_bound_utc():
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert format_oanda_bound(when) == "2026-01-02T03:04:05.000000000Z"
