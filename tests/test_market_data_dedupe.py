from __future__ import annotations

from datetime import datetime, timezone

from brokerai.db.repositories.market_data import _dedupe_candle_rows


def test_dedupe_candle_rows_by_utc_second():
    same_open = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        {"ts": same_open, "time": "2026-01-01T12:00:00.000000000Z", "close": 1.0},
        {"ts": same_open, "time": "2026-01-01T12:00:00.000000001Z", "close": 1.1},
        {
            "ts": datetime(2026, 1, 1, 12, 15, tzinfo=timezone.utc),
            "time": "2026-01-01T12:15:00.000000000Z",
            "close": 2.0,
        },
    ]
    deduped = _dedupe_candle_rows(rows)
    assert len(deduped) == 2
    assert deduped[0]["close"] == 1.0
    assert deduped[1]["close"] == 2.0
