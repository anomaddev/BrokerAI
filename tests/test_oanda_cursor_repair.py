from __future__ import annotations

from datetime import datetime, timezone

from brokerai.trading.oanda_cursor_repair import as_utc_aware


def test_as_utc_aware_parses_iso_string():
    result = as_utc_aware("2026-07-17T21:30:00+00:00")
    assert result == datetime(2026, 7, 17, 21, 30, tzinfo=timezone.utc)


def test_as_utc_aware_parses_zulu_string():
    result = as_utc_aware("2026-07-17T21:30:00Z")
    assert result == datetime(2026, 7, 17, 21, 30, tzinfo=timezone.utc)


def test_as_utc_aware_accepts_datetime():
    naive = datetime(2026, 7, 17, 21, 30)
    assert as_utc_aware(naive) == datetime(2026, 7, 17, 21, 30, tzinfo=timezone.utc)


def test_as_utc_aware_rejects_invalid_string():
    assert as_utc_aware("not-a-date") is None
    assert as_utc_aware("") is None
    assert as_utc_aware(None) is None
