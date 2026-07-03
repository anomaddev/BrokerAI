from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_migration_overlay_backfill():
    with patch("brokerai.db.client.get_db") as mock_get_db, patch(
        "brokerai.db.client.close_db",
        new=AsyncMock(),
    ):
        handle = MagicMock()
        mock_get_db.return_value = handle
        find_result = MagicMock()
        find_result.to_list = AsyncMock(
            return_value=[
                {
                    "id": "legacy-1",
                    "broker_order_id": "565",
                    "strategy_id": "strat-a",
                    "strategy_name": "EMA",
                    "status": "closed",
                    "pair": "EUR/JPY",
                    "direction": "short",
                    "units": -683,
                    "entry_price": 184.0,
                }
            ]
        )
        handle.db.trades.find.return_value = find_result
        handle.db.broker_lots.find_one = AsyncMock(
            return_value={
                "id": "lot-565",
                "account_id": "101-001-test",
                "broker_lot_id": "565",
                "state": "open",
                "raw_broker": {"id": "565", "state": "OPEN"},
            }
        )
        handle.db.broker_lots.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        handle.db.trades.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))

        from scripts.migrate_trades_to_broker_lots import migrate

        stats = await migrate(purge_legacy=True)
        assert stats["overlay_applied"] == 1
        assert stats["purged"] == 1
        handle.db.broker_lots.update_one.assert_called_once()


def test_legacy_trade_to_lot_doc_maps_units():
    from brokerai.db.migrations.legacy_trades_to_lots import legacy_trade_to_lot_doc

    doc = legacy_trade_to_lot_doc(
        {
            "id": "legacy-1",
            "status": "closed",
            "pair": "EUR/USD",
            "direction": "long",
            "units": -1000,
            "entry_price": 1.1,
            "broker_order_id": "99",
        }
    )
    assert doc["initial_qty"] == 1000
    assert doc["current_qty"] == 0
    assert doc["broker_lot_id"] == "99"
    assert doc["state"] == "closed"


def test_pick_best_legacy_prefers_strategy_over_import():
    from brokerai.db.migrations.legacy_trades_to_lots import pick_best_legacy_per_broker

    now = datetime.now(timezone.utc)
    trades = [
        {
            "id": "import",
            "broker_order_id": "565",
            "strategy_id": "oanda-import",
            "updated_at": now,
        },
        {
            "id": "strategy",
            "broker_order_id": "565",
            "strategy_id": "ema-strat",
            "updated_at": now,
        },
    ]
    picked = pick_best_legacy_per_broker(trades)
    assert picked["565"]["id"] == "strategy"
