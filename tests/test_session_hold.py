"""Tests for effective-session coverage and major-market close helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from brokerai.trading.session_hold import (
    effective_session_ids,
    hours_until_major_market_close,
    is_effective_session_coverage,
    is_within_major_market_close_window,
    next_major_market_close,
    should_block_late_market_entry,
    should_force_close_market,
    should_force_close_session_boundary,
    would_leave_coverage_on_next_candle,
)

ET = ZoneInfo("America/New_York")


def _params(sessions: list[str], **execution) -> dict:
    return {
        "execution": {
            "sessions": sessions,
            "min_confidence": 60,
            "dont_hold_between_sessions": False,
            "dont_hold_between_markets": False,
            "close_before_market_hours": 2,
            "no_late_market_trading": False,
            "late_market_hours": 2,
            **execution,
        }
    }


def test_effective_session_ids_intersection():
    asset = {"sydney": True, "asia": True, "london": True, "ny": False}
    params = _params(["London", "NY"])
    assert effective_session_ids(asset, params) == {"london"}


def test_effective_session_ids_strategy_only_ignored_when_globally_off():
    asset = {"sydney": False, "asia": False, "london": False, "ny": True}
    params = _params(["London"])
    assert effective_session_ids(asset, params) == set()


def test_next_major_market_close_ny_friday_1700_et():
    # Wednesday before a Friday close week.
    when = datetime(2026, 7, 15, 12, 0, tzinfo=ET)  # Wed
    close = next_major_market_close(when, {"london", "ny"})
    assert close is not None
    close_et = close.astimezone(ET)
    assert close_et.weekday() == 4
    assert (close_et.hour, close_et.minute) == (17, 0)


def test_next_major_market_close_london_only_friday_1200_et():
    when = datetime(2026, 7, 15, 12, 0, tzinfo=ET)
    close = next_major_market_close(when, {"london"})
    assert close is not None
    close_et = close.astimezone(ET)
    assert close_et.weekday() == 4
    assert (close_et.hour, close_et.minute) == (12, 0)


def test_daily_break_is_not_major_market_close():
    # Thursday 16:30 ET — next major close is Friday, not today's 17:00 break.
    when = datetime(2026, 7, 16, 16, 30, tzinfo=ET)
    close = next_major_market_close(when, {"ny"})
    assert close is not None
    close_et = close.astimezone(ET)
    assert close_et.date().isoformat() == "2026-07-17"
    assert (close_et.hour, close_et.minute) == (17, 0)


def test_london_ny_overlap_does_not_leave_coverage():
    # 11:45 ET Friday — London ending soon but NY still open.
    when = datetime(2026, 7, 17, 11, 45, tzinfo=ET)
    assert is_effective_session_coverage(when, {"london", "ny"}) is True
    assert would_leave_coverage_on_next_candle(when, "M15", {"london", "ny"}) is False


def test_london_only_leaves_coverage_near_noon():
    # Last M15 bar still inside London (ends 12:00 ET): 11:45 open.
    when = datetime(2026, 7, 17, 11, 45, tzinfo=ET)
    assert is_effective_session_coverage(when, {"london"}) is True
    assert would_leave_coverage_on_next_candle(when, "M15", {"london"}) is True


def test_should_force_close_session_boundary_respects_toggle():
    when = datetime(2026, 7, 17, 11, 45, tzinfo=ET)
    asset = {"sydney": True, "asia": True, "london": True, "ny": True}
    off = _params(["London"], dont_hold_between_sessions=False)
    on = _params(["London"], dont_hold_between_sessions=True)
    assert (
        should_force_close_session_boundary(
            off, when=when, timeframe="M15", asset_enabled_sessions=asset
        )
        is False
    )
    assert (
        should_force_close_session_boundary(
            on, when=when, timeframe="M15", asset_enabled_sessions=asset
        )
        is True
    )


def test_should_force_close_market_within_hours():
    # Friday 15:30 ET with NY — 1.5h before 17:00, within 2h window.
    when = datetime(2026, 7, 17, 15, 30, tzinfo=ET)
    asset = {"sydney": True, "asia": True, "london": True, "ny": True}
    params = _params(
        ["London", "NY"],
        dont_hold_between_markets=True,
        close_before_market_hours=2,
    )
    assert should_force_close_market(params, when=when, asset_enabled_sessions=asset) is True
    remaining = hours_until_major_market_close(when, {"london", "ny"})
    assert remaining is not None
    assert 1.0 < remaining <= 2.0


def test_late_market_entry_blocked_near_close():
    when = datetime(2026, 7, 17, 15, 30, tzinfo=ET)
    asset = {"sydney": True, "asia": True, "london": True, "ny": True}
    params = _params(
        ["London", "NY"],
        no_late_market_trading=True,
        late_market_hours=2,
    )
    blocked, details = should_block_late_market_entry(
        params, when=when, asset_enabled_sessions=asset
    )
    assert blocked is True
    assert details["late_market_hours"] == 2


def test_late_market_entry_allowed_midweek():
    when = datetime(2026, 7, 15, 12, 0, tzinfo=ET)  # Wednesday
    asset = {"sydney": True, "asia": True, "london": True, "ny": True}
    params = _params(
        ["London", "NY"],
        no_late_market_trading=True,
        late_market_hours=2,
    )
    blocked, _ = should_block_late_market_entry(
        params, when=when, asset_enabled_sessions=asset
    )
    assert blocked is False
    assert is_within_major_market_close_window(when, 2, {"london", "ny"}) is False
