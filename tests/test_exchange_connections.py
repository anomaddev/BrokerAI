from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository, OANDA_ID


@pytest.mark.asyncio
async def test_get_connection_defaults_for_oanda():
    repo = ExchangeConnectionsRepository()
    db_handle = MagicMock()
    db_handle.db = {repo.COLLECTION: MagicMock()}
    db_handle.db[repo.COLLECTION].find_one = AsyncMock(return_value=None)

    with patch(
        "brokerai.db.repositories.exchange_connections.get_db",
        new=AsyncMock(return_value=db_handle),
    ):
        doc = await repo.get_connection(OANDA_ID)

    assert doc["exchange_id"] == OANDA_ID
    assert doc["access_token"] == ""
    assert doc["environment"] == "practice"


@pytest.mark.asyncio
async def test_save_oanda_delegates_to_save_connection():
    repo = ExchangeConnectionsRepository()
    with patch.object(repo, "save_connection", new=AsyncMock(return_value={"exchange_id": OANDA_ID})) as mock_save:
        await repo.save_oanda(access_token="tok", environment="practice", account_id="acc")

    mock_save.assert_awaited_once_with(
        OANDA_ID,
        access_token="tok",
        environment="practice",
        account_id="acc",
    )
