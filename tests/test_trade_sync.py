from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.trade_sync import (
    BROKER_CLOSED_REASON,
    _parse_broker_open_time,
    broker_closed_trade_to_ledger_close,
    broker_trade_to_ledger_intent,
    sync_oanda_trades_to_ledger,
)


def _sync_result(**overrides):
    defaults = {
        "configured": True,
        "lots_upserted": 0,
        "enriched": 0,
        "lots_closed": 0,
        "skipped_reason": None,
        "backfilled": 0,
        "backfilled_lot_ids": [],
        "to_dict": lambda self: {
            "configured": self.configured,
            "imported": self.lots_upserted,
            "updated": self.enriched,
            "closed": self.lots_closed,
            "backfilled": self.backfilled,
            "backfilled_lot_ids": list(self.backfilled_lot_ids),
        },
    }
    defaults.update(overrides)
    return type("R", (), defaults)()


def test_parse_broker_open_time_handles_nanoseconds():
    parsed = _parse_broker_open_time("2026-06-30T12:00:00.123456789Z")
    assert parsed == datetime(2026, 6, 30, 12, 0, 0, 123456, tzinfo=timezone.utc)


def test_broker_trade_to_ledger_intent_short_units_are_negative():
    intent = broker_trade_to_ledger_intent(
        {
            "id": "broker-1",
            "pair": "EUR/USD",
            "direction": "short",
            "units": 500,
            "price": 1.10123,
            "open_time": "2026-06-30T12:00:00.000000000Z",
        }
    )
    assert intent["units"] == -500
    assert intent["broker_lot_id"] == "broker-1"
    assert intent["strategy_id"] == "oanda-import"
    assert intent["metadata"]["source"] == "oanda_sync"


def test_broker_closed_trade_to_ledger_close_maps_fields():
    close_kwargs = broker_closed_trade_to_ledger_close(
        {
            "id": "broker-1",
            "exit_price": 1.105,
            "realized_pl": -2.5,
            "open_time": "2026-06-30T12:00:00.000000000Z",
            "close_time": "2026-06-30T14:30:00.000000000Z",
            "closed_at": datetime(2026, 6, 30, 14, 30, tzinfo=timezone.utc),
        }
    )
    assert close_kwargs["reason"] == BROKER_CLOSED_REASON
    assert close_kwargs["exit_price"] == 1.105
    assert close_kwargs["realized_pl"] == -2.5
    assert close_kwargs["metadata"]["broker_trade_id"] == "broker-1"


@pytest.mark.asyncio
async def test_sync_skips_when_oanda_unconfigured():
    with patch(
        "brokerai.trading.trade_sync.run_broker_sync",
        new=AsyncMock(return_value=_sync_result(configured=False)),
    ):
        result = await sync_oanda_trades_to_ledger()

    assert result["configured"] is False
    assert result["imported"] == 0


@pytest.mark.asyncio
async def test_sync_imports_unmatched_broker_trade():
    with patch(
        "brokerai.trading.trade_sync.run_broker_sync",
        new=AsyncMock(return_value=_sync_result(lots_upserted=1)),
    ):
        result = await sync_oanda_trades_to_ledger()

    assert result["imported"] == 1


@pytest.mark.asyncio
async def test_sync_is_idempotent_when_broker_order_id_exists():
    with patch(
        "brokerai.trading.trade_sync.run_broker_sync",
        new=AsyncMock(return_value=_sync_result(skipped_reason="recent_sync")),
    ):
        result = await sync_oanda_trades_to_ledger()

    assert result["imported"] == 0
    assert result["skipped"] == 1


@pytest.mark.asyncio
async def test_sync_backfills_broker_order_id_on_pair_direction_match():
    with patch(
        "brokerai.trading.trade_sync.run_broker_sync",
        new=AsyncMock(return_value=_sync_result(enriched=1)),
    ):
        result = await sync_oanda_trades_to_ledger()

    assert result["imported"] == 0
    assert result["updated"] == 1


@pytest.mark.asyncio
async def test_sync_closes_ledger_trade_closed_on_broker():
    with patch(
        "brokerai.trading.trade_sync.run_broker_sync",
        new=AsyncMock(return_value=_sync_result(lots_closed=1)),
    ):
        result = await sync_oanda_trades_to_ledger()

    assert result["closed"] == 1


@pytest.mark.asyncio
async def test_sync_reports_backfilled_from_broker_sync():
    with patch(
        "brokerai.trading.trade_sync.run_broker_sync",
        new=AsyncMock(
            return_value=_sync_result(
                backfilled=1,
                backfilled_lot_ids=["closed-ledger-1"],
            )
        ),
    ):
        result = await sync_oanda_trades_to_ledger()

    assert result["backfilled"] == 1
    assert result["backfilled_lot_ids"] == ["closed-ledger-1"]
