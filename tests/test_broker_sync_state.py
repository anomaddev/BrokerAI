from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from brokerai.db.repositories.broker_sync_state import BrokerSyncStateRepository, _parse_doc_time


pytestmark = pytest.mark.usefixtures("sqlite_db")


@pytest.mark.asyncio
async def test_try_acquire_sync_lock_updates_existing_row():
    repo = BrokerSyncStateRepository()
    await repo.set_state("oanda", "acc-1", sync_cursor="cursor-1")

    acquired = await repo.try_acquire_sync_lock("oanda", "acc-1", holder="worker-a")

    assert acquired is True
    state = await repo.get_state("oanda", "acc-1")
    assert state is not None
    assert state["sync_lock_holder"] == "worker-a"


@pytest.mark.asyncio
async def test_try_acquire_sync_lock_inserts_when_row_missing():
    repo = BrokerSyncStateRepository()

    acquired = await repo.try_acquire_sync_lock("oanda", "acc-1", holder="worker-a")

    assert acquired is True
    state = await repo.get_state("oanda", "acc-1")
    assert state is not None
    assert state["sync_lock_holder"] == "worker-a"


@pytest.mark.asyncio
async def test_try_acquire_sync_lock_returns_false_when_lock_held():
    repo = BrokerSyncStateRepository()
    now = datetime.now(timezone.utc)
    await repo.try_acquire_sync_lock("oanda", "acc-1", holder="worker-a", ttl_seconds=300)

    acquired = await repo.try_acquire_sync_lock("oanda", "acc-1", holder="worker-b", ttl_seconds=300)

    assert acquired is False
    state = await repo.get_state("oanda", "acc-1")
    assert state is not None
    assert state["sync_lock_holder"] == "worker-a"
    expires = _parse_doc_time(state["sync_lock_expires_at"])
    assert expires is not None
    assert expires > now


@pytest.mark.asyncio
async def test_try_acquire_sync_lock_retries_update_after_insert_race():
    repo = BrokerSyncStateRepository()
    await repo.set_state("oanda", "acc-1", sync_cursor="seed")

    acquired = await repo.try_acquire_sync_lock("oanda", "acc-1", holder="worker-a")

    assert acquired is True
    state = await repo.get_state("oanda", "acc-1")
    assert state is not None
    assert state["sync_lock_holder"] == "worker-a"
    expires = _parse_doc_time(state["sync_lock_expires_at"])
    assert expires is not None
    assert expires > datetime.now(timezone.utc) - timedelta(seconds=5)
