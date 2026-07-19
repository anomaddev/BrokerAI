from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from brokerai.db.repositories.instrument_exposure import (
    InstrumentExposureRepository,
    _rollup_from_lot_docs,
    serialize_exposure_rollup,
)
from brokerai.trading.broker.models import InstrumentExposure


pytestmark = pytest.mark.usefixtures("sqlite_db")


def test_rollup_from_open_lot_docs_groups_by_symbol_and_direction():
    lots = [
        {
            "account_id": "acct",
            "state": "open",
            "symbol": "EUR_USD",
            "direction": "long",
            "current_qty": 1000,
            "entry_price": 1.1,
            "unrealized_pl": 5.0,
            "broker_lot_id": "1",
        },
        {
            "account_id": "acct",
            "state": "open",
            "symbol": "EUR_USD",
            "direction": "long",
            "current_qty": 500,
            "entry_price": 1.2,
            "unrealized_pl": 2.0,
            "broker_lot_id": "2",
        },
        {
            "account_id": "acct",
            "state": "closed",
            "symbol": "EUR_USD",
            "direction": "long",
            "current_qty": 0,
            "entry_price": 1.1,
            "broker_lot_id": "3",
        },
    ]
    rollups = _rollup_from_lot_docs(lots, exchange_id="oanda")
    assert len(rollups) == 1
    assert rollups[0].symbol == "EUR_USD"
    assert rollups[0].total_qty == 1500
    assert rollups[0].broker_lot_ids == ["1", "2"]


@pytest.mark.asyncio
async def test_instrument_exposure_repository_recompute():
    repo = InstrumentExposureRepository()
    count = await repo.recompute_for_account(
        exchange_id="oanda",
        account_id="acct",
        open_lots=[
            {
                "account_id": "acct",
                "state": "open",
                "symbol": "EUR_USD",
                "direction": "long",
                "current_qty": 1000,
                "entry_price": 1.1,
                "unrealized_pl": 1.0,
                "broker_lot_id": "1",
            }
        ],
    )
    assert count == 1

    stored = await repo.list_for_account(exchange_id="oanda", account_id="acct")
    assert stored[0]["symbol"] == "EUR_USD"
    assert stored[0]["total_qty"] == 1000

    local = InstrumentExposureRepository.rollups_to_local_by_key(
        [doc for doc in stored]
    )
    assert local[("EUR_USD", "long")] == 1000

    exposure = InstrumentExposure(
        exchange_id="oanda",
        symbol="EUR_USD",
        direction="long",
        total_qty=1000,
        average_price=1.1,
        unrealized_pl=1.0,
        broker_lot_ids=["1"],
    )
    serialized = serialize_exposure_rollup(exposure.to_dict())
    assert serialized["pair"] == "EUR/USD"
    assert serialized["total_qty"] == 1000

    await repo.upsert_rollup(exposure, account_id="acct")
    roundtrip = await repo.get_for_symbol(
        exchange_id="oanda",
        account_id="acct",
        symbol="EUR_USD",
        direction="long",
    )
    assert roundtrip is not None
    assert roundtrip.total_qty == 1000

    payload = json.loads(json.dumps(serialized, default=str))
    assert payload["symbol"] == "EUR_USD"
