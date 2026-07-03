from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.oanda_account_sync import run_oanda_account_sync


@pytest.mark.asyncio
async def test_run_oanda_account_sync_unconfigured():
    with patch(
        "brokerai.trading.oanda_account_sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "",
            "account_id": "",
            "environment": "practice",
        }

        result = await run_oanda_account_sync(force=True)

    assert result.configured is False
    assert result.skipped_reason == "not_configured"


@pytest.mark.asyncio
async def test_run_oanda_account_sync_persists_accounts_and_summary():
    synced_at = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    summary = {
        "id": "101-001-test",
        "alias": "Primary",
        "currency": "USD",
        "balance": "10000.00",
        "nav": "10050.00",
        "unrealized_pl": "50.00",
        "realized_pl": "0.00",
        "margin_available": "9500.00",
        "margin_used": "500.00",
        "open_trade_count": 1,
        "open_position_count": 1,
        "pending_order_count": 0,
    }
    accounts = [{"id": "101-001-test", "tags": []}]

    with patch(
        "brokerai.trading.oanda_account_sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch(
        "brokerai.trading.oanda_account_sync.list_accounts",
        new=AsyncMock(return_value=accounts),
    ), patch(
        "brokerai.trading.oanda_account_sync.get_account_summary",
        new=AsyncMock(return_value=summary),
    ), patch(
        "brokerai.trading.oanda_account_sync.OandaAccountSnapshotsRepository",
    ) as mock_repo_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "101-001-test",
            "environment": "practice",
        }

        snapshots_repo = AsyncMock()
        mock_repo_cls.return_value = snapshots_repo

        with patch(
            "brokerai.trading.oanda_account_sync.datetime",
        ) as mock_datetime:
            mock_datetime.now.return_value = synced_at
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            result = await run_oanda_account_sync(force=True)

    assert result.configured is True
    assert result.summary_synced is True
    assert result.account_id == "101-001-test"
    assert result.accounts_count == 1
    snapshots_repo.upsert_accounts_snapshot.assert_awaited_once()
    snapshots_repo.insert_summary_snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_oanda_account_sync_skips_recent_sync():
    import brokerai.trading.oanda_account_sync as sync_module

    sync_module._LAST_SUCCESSFUL_SYNC = datetime.now(timezone.utc)

    with patch(
        "brokerai.trading.oanda_account_sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch(
        "brokerai.trading.oanda_account_sync.list_accounts",
        new=AsyncMock(),
    ) as mock_list_accounts:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "101-001-test",
            "environment": "practice",
        }

        result = await run_oanda_account_sync(force=False)

    assert result.skipped_reason == "recent_sync"
    mock_list_accounts.assert_not_awaited()
    sync_module._LAST_SUCCESSFUL_SYNC = None


@pytest.mark.asyncio
async def test_get_cached_oanda_account_summary_returns_latest():
    from brokerai.db.repositories.oanda_account_snapshots import OandaAccountSnapshotsRepository
    from brokerai.trading.oanda_account_sync import get_cached_oanda_account_summary

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
