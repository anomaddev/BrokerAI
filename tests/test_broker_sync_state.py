from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import DuplicateKeyError

from brokerai.db.repositories.broker_sync_state import BrokerSyncStateRepository


def _collection(*, update_results: list[MagicMock], insert_error: Exception | None = None):
    update_calls: list[tuple[dict, dict]] = []
    insert_calls: list[dict] = []

    async def update_one(filter_doc, update_doc):
        update_calls.append((filter_doc, update_doc))
        return update_results.pop(0)

    async def insert_one(doc):
        insert_calls.append(doc)
        if insert_error is not None:
            raise insert_error

    collection = MagicMock()
    collection.update_one = AsyncMock(side_effect=update_one)
    collection.insert_one = AsyncMock(side_effect=insert_one)
    collection._update_calls = update_calls
    collection._insert_calls = insert_calls
    return collection


def _db_handle(collection: MagicMock):
    db = MagicMock()
    db.__getitem__.return_value = collection
    handle = MagicMock()
    handle.db = db
    return handle


@pytest.mark.asyncio
async def test_try_acquire_sync_lock_updates_existing_row():
    collection = _collection(update_results=[MagicMock(modified_count=1)])
    repo = BrokerSyncStateRepository()

    with patch(
        "brokerai.db.repositories.broker_sync_state.get_db",
        AsyncMock(return_value=_db_handle(collection)),
    ):
        acquired = await repo.try_acquire_sync_lock("oanda", "acc-1", holder="worker-a")

    assert acquired is True
    assert len(collection._update_calls) == 1
    assert collection.insert_one.await_count == 0
    filter_doc, update_doc = collection._update_calls[0]
    assert filter_doc["exchange_id"] == "oanda"
    assert filter_doc["account_id"] == "acc-1"
    assert update_doc["$set"]["sync_lock_holder"] == "worker-a"


@pytest.mark.asyncio
async def test_try_acquire_sync_lock_inserts_when_row_missing():
    collection = _collection(update_results=[MagicMock(modified_count=0)])
    repo = BrokerSyncStateRepository()

    with patch(
        "brokerai.db.repositories.broker_sync_state.get_db",
        AsyncMock(return_value=_db_handle(collection)),
    ):
        acquired = await repo.try_acquire_sync_lock("oanda", "acc-1", holder="worker-a")

    assert acquired is True
    assert len(collection._update_calls) == 1
    assert len(collection._insert_calls) == 1
    assert collection._insert_calls[0]["exchange_id"] == "oanda"
    assert collection._insert_calls[0]["sync_lock_holder"] == "worker-a"


@pytest.mark.asyncio
async def test_try_acquire_sync_lock_returns_false_when_lock_held():
    collection = _collection(
        update_results=[
            MagicMock(modified_count=0),
            MagicMock(modified_count=0),
        ],
        insert_error=DuplicateKeyError("dup"),
    )
    repo = BrokerSyncStateRepository()

    with patch(
        "brokerai.db.repositories.broker_sync_state.get_db",
        AsyncMock(return_value=_db_handle(collection)),
    ):
        acquired = await repo.try_acquire_sync_lock("oanda", "acc-1", holder="worker-a")

    assert acquired is False
    assert len(collection._update_calls) == 2
    assert len(collection._insert_calls) == 1


@pytest.mark.asyncio
async def test_try_acquire_sync_lock_retries_update_after_insert_race():
    collection = _collection(
        update_results=[
            MagicMock(modified_count=0),
            MagicMock(modified_count=1),
        ],
        insert_error=DuplicateKeyError("dup"),
    )
    repo = BrokerSyncStateRepository()

    with patch(
        "brokerai.db.repositories.broker_sync_state.get_db",
        AsyncMock(return_value=_db_handle(collection)),
    ):
        acquired = await repo.try_acquire_sync_lock("oanda", "acc-1", holder="worker-a")

    assert acquired is True
    assert len(collection._update_calls) == 2