from __future__ import annotations

from unittest.mock import patch

import pytest

from brokerai.db.repositories.instrument_exposure import (
    InstrumentExposureRepository,
    _rollup_from_lot_docs,
)
from brokerai.trading.broker.models import InstrumentExposure


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
    stored: list[dict] = []

    class FakeCursor:
        def sort(self, *_args, **_kwargs):
            return self

        async def to_list(self, length=500):
            return list(stored)

    class FakeCollection:
        async def delete_many(self, _query):
            stored.clear()

        async def find_one(self, _query, _projection):
            return None

        async def update_one(self, _key, update, upsert=False):
            stored.append({**update["$set"]})

        def find(self, _query, _projection):
            return FakeCursor()

    class FakeDb:
        def __getitem__(self, name):
            assert name == InstrumentExposureRepository.COLLECTION
            return FakeCollection()

    class FakeHandle:
        db = FakeDb()

    async def fake_get_db():
        return FakeHandle()

    with patch(
        "brokerai.db.repositories.instrument_exposure.get_db",
        new=fake_get_db,
    ):
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
    assert stored[0]["symbol"] == "EUR_USD"
    assert stored[0]["total_qty"] == 1000

    local = InstrumentExposureRepository.rollups_to_local_by_key(stored)
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
    assert exposure.to_dict()["pair"] == "EUR/USD"
