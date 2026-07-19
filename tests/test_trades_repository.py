from __future__ import annotations

from datetime import datetime, timezone

from brokerai.db.repositories.broker_lots import serialize_lot


def test_serialize_lot_formats_datetimes():
    doc = {
        "id": "trade-1",
        "strategy_id": "s1",
        "strategy_name": "EMA",
        "pair": "EUR/USD",
        "asset_class": "forex",
        "direction": "long",
        "entry_price": 1.1,
        "stop_loss": 1.09,
        "take_profit": 1.12,
        "exit_mode": "rr_ratio",
        "risk_pct": 1.0,
        "initial_qty": 1000,
        "current_qty": 1000,
        "confidence": 0.8,
        "state": "open",
        "broker_lot_id": "123",
        "symbol": "EUR_USD",
        "metadata": {},
        "trade_date": "2026-06-30",
        "open_time": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        "close_time": None,
        "synced_at": "2026-06-30T12:05:00+00:00",
        "created_at": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
    }
    serialized = serialize_lot(doc)
    assert serialized["open_time"] == "2026-06-30T12:00:00+00:00"
    assert serialized["close_time"] is None
    assert serialized["synced_at"] == "2026-06-30T12:05:00+00:00"


def test_list_lots_all_sorted_open_first_then_last_modified():
    from brokerai.db.repositories.broker_lots import _sort_lots_for_display

    rows = [
        {
            "id": "open-old",
            "state": "open",
            "open_time": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
            "initial_qty": 1,
            "current_qty": 1,
            "direction": "long",
            "entry_price": 1.0,
        },
        {
            "id": "open-new",
            "state": "open",
            "open_time": datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
            "initial_qty": 1,
            "current_qty": 1,
            "direction": "long",
            "entry_price": 1.0,
        },
        {
            "id": "closed-newest",
            "state": "closed",
            "close_time": datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc),
            "initial_qty": 1,
            "current_qty": 0,
            "direction": "long",
            "entry_price": 1.0,
        },
    ]

    sorted_rows = _sort_lots_for_display(
        [serialize_lot(row) for row in rows],
        open_first=True,
    )
    assert [row["id"] for row in sorted_rows] == ["open-new", "open-old", "closed-newest"]
