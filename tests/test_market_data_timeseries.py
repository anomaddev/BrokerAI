from __future__ import annotations

from datetime import datetime, timezone

from brokerai.db.market_data_timeseries import (
    candle_open_time_from_document,
    candle_to_timeseries_document,
    meta_query_filter,
    timeseries_document_to_candle,
)


def test_meta_query_filter():
    assert meta_query_filter("EUR/USD", "M15", "oanda") == {
        "meta.symbol": "EUR/USD",
        "meta.timeframe": "M15",
        "meta.source": "oanda",
    }


def test_candle_to_timeseries_document_preserves_oanda_time_string():
    fetched_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    document = candle_to_timeseries_document(
        "EUR/USD",
        "M15",
        "oanda",
        {
            "time": "2026-01-01T12:00:00.000000000Z",
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 12,
        },
        fetched_at=fetched_at,
    )
    assert document is not None
    assert document["meta"] == {
        "symbol": "EUR/USD",
        "timeframe": "M15",
        "source": "oanda",
    }
    assert document["time"] == "2026-01-01T12:00:00.000000000Z"
    assert document["ts"] == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert document["close"] == 1.15


def test_candle_open_time_from_document_time_only_projection():
    assert (
        candle_open_time_from_document(
            {
                "ts": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
                "time": "2026-01-01T12:00:00.000000000Z",
            }
        )
        == "2026-01-01T12:00:00.000000000Z"
    )


def test_timeseries_document_to_candle_round_trip():
    fetched_at = datetime(2026, 2, 2, 9, 0, tzinfo=timezone.utc)
    document = candle_to_timeseries_document(
        "GBP/USD",
        "H1",
        "oanda",
        {
            "time": "2026-02-02T08:00:00.000000000Z",
            "open": 1.25,
            "high": 1.26,
            "low": 1.24,
            "close": 1.255,
            "volume": 0,
        },
        fetched_at=fetched_at,
    )
    assert document is not None
    round_trip = timeseries_document_to_candle(document)
    assert round_trip["symbol"] == "GBP/USD"
    assert round_trip["timeframe"] == "H1"
    assert round_trip["time"] == "2026-02-02T08:00:00.000000000Z"
    assert round_trip["close"] == 1.255
