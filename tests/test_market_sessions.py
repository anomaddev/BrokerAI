from __future__ import annotations

from datetime import datetime, timezone

from brokerai.integrations.massive import build_session_snapshot
from brokerai.market_sessions import TRADING_SESSIONS, session_status


def _ny_session():
    return next(session for session in TRADING_SESSIONS if session.id == "ny")


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
    london = next(session for session in TRADING_SESSIONS if session.id == "london")
    payload = session_status(london, when, fx_open=True)
    assert payload["status"] == "closed"


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
