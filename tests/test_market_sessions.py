from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from brokerai.integrations.massive import build_session_snapshot
from brokerai.market_sessions import (
    TRADING_SESSIONS,
    is_forex_hours,
    is_session_active,
    normalize_market_indicators,
    session_status,
)

ET = ZoneInfo("America/New_York")


def _ny_session():
    return next(session for session in TRADING_SESSIONS if session.id == "ny")


def _session(session_id: str):
    return next(session for session in TRADING_SESSIONS if session.id == session_id)


def test_normalize_market_indicators_defaults_four_sessions():
    sessions = normalize_market_indicators(None)
    assert sessions == {
        "sydney": True,
        "asia": True,
        "london": True,
        "ny": True,
    }


def test_normalize_market_indicators_migrates_legacy_tokyo_singapore():
    sessions = normalize_market_indicators({"tokyo": False, "singapore": True, "london": True})
    assert sessions["asia"] is True
    assert sessions["sydney"] is True


def test_ny_closed_on_sunday_when_api_reports_fx_open():
    when = datetime(2026, 6, 28, 18, 0, tzinfo=timezone.utc)
    payload = session_status(
        _ny_session(),
        when,
        fx_open=True,
        exchange_status="closed",
    )
    assert payload["status"] == "closed"


def test_ny_open_during_regular_hours():
    when = datetime(2026, 6, 29, 15, 0, tzinfo=timezone.utc)
    payload = session_status(
        _ny_session(),
        when,
        fx_open=True,
        exchange_status="open",
    )
    assert payload["status"] == "open"


def test_ny_extended_hours():
    when = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)
    payload = session_status(
        _ny_session(),
        when,
        fx_open=True,
        exchange_status="extended-hours",
    )
    assert payload["status"] == "open"
    assert payload["exchange_status"] == "extended-hours"


def test_forex_sessions_respect_weekend_hours_despite_api_fx_open():
    when = datetime(2026, 6, 28, 18, 0, tzinfo=timezone.utc)
    london = _session("london")
    payload = session_status(london, when, fx_open=True)
    assert payload["status"] == "closed"


def test_sydney_open_sunday_evening_et():
    when = datetime(2026, 7, 5, 21, 20, tzinfo=timezone.utc)  # Sun 5:20 PM ET
    assert is_forex_hours(when) is True
    assert is_session_active(_session("sydney"), when) is True
    assert is_session_active(_session("asia"), when) is False


def test_asia_open_wednesday_morning_et():
    when = datetime(2026, 3, 4, 7, 30, tzinfo=timezone.utc)  # Wed 3:30 AM ET / 07:30 UTC
    assert is_session_active(_session("asia"), when) is True


def test_asia_closed_after_9_utc():
    when = datetime(2026, 3, 4, 9, 0, tzinfo=timezone.utc)
    assert is_session_active(_session("asia"), when) is False


def test_london_ny_overlap_wednesday_morning():
    when = datetime(2026, 3, 4, 14, 0, tzinfo=timezone.utc)  # Wed 10:00 AM ET
    assert is_session_active(_session("london"), when) is True
    assert is_session_active(_session("ny"), when) is True


def test_sydney_wraparound_session_close_is_next_morning():
    when = datetime(2026, 3, 4, 23, 0, tzinfo=timezone.utc)  # Wed 6:00 PM ET
    sydney = _session("sydney")
    payload = session_status(sydney, when, fx_open=True)
    assert payload["status"] == "open"
    close_at = datetime.fromisoformat(payload["closes_at"])
    assert close_at.astimezone(ET).hour == 2


def test_build_session_snapshot_uses_nyse_status():
    payload = build_session_snapshot(
        {
            "serverTime": "2026-06-28T18:00:00Z",
            "currencies": {"fx": "open"},
            "exchanges": {"nyse": "closed"},
            "market": "closed",
        }
    )
    ny = next(session for session in payload["sessions"] if session["id"] == "ny")
    assert ny["status"] == "closed"
