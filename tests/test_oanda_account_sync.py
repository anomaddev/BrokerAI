from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.broker.models import SyncResult
from brokerai.trading.oanda_account_sync import get_cached_oanda_account_summary, run_oanda_account_sync


@pytest.mark.asyncio
async def test_run_oanda_account_sync_unconfigured():
    with patch(
        "brokerai.trading.oanda_account_sync.run_broker_sync",
        new=AsyncMock(
            return_value=SyncResult(configured=False, mode="incremental", skipped_reason="not_configured")
        ),
    ):
        result = await run_oanda_account_sync(force=True)

    assert result.configured is False


@pytest.mark.asyncio
async def test_run_oanda_account_sync_delegates_to_broker_sync():
    sync_result = SyncResult(
        configured=True,
        mode="incremental",
        summary_synced=True,
        account_id="101-001-test",
        cursor_before="566",
        cursor_after="567",
        changes_applied={"transactions": 1},
        repair_triggered=False,
    )

    with patch(
        "brokerai.trading.oanda_account_sync.run_broker_sync",
        new=AsyncMock(return_value=sync_result),
    ) as mock_sync:
        result = await run_oanda_account_sync(force=True)

    mock_sync.assert_awaited_once_with(
        exchange_id="oanda",
        mode="incremental",
        force=True,
        include_account_summary=True,
        fetch_live_prices=False,
    )
    assert result.summary_synced is True
    assert result.account_id == "101-001-test"
    assert result.cursor_after == "567"


@pytest.mark.asyncio
async def test_get_cached_oanda_account_summary_returns_latest():
    from brokerai.db.repositories.oanda_account_snapshots import OandaAccountSnapshotsRepository

    stored = {
        "account_id": "101-001-test",
        "id": "101-001-test",
        "balance": "10000.00",
        "synced_at": datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc),
    }

    with patch(
        "brokerai.trading.oanda_account_sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch.object(
        OandaAccountSnapshotsRepository,
        "get_latest_summary",
        new=AsyncMock(return_value=stored),
    ), patch(
        "brokerai.trading.oanda_account_sync.run_oanda_account_sync",
        new=AsyncMock(),
    ) as mock_sync:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "101-001-test",
            "environment": "practice",
        }

        summary = await get_cached_oanda_account_summary(force_sync_if_missing=False)

    assert summary is not None
    assert summary["balance"] == "10000.00"
    mock_sync.assert_not_awaited()
