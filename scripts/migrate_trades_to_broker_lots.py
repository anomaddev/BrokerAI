#!/usr/bin/env python3
"""Migrate legacy ``trades`` rows into ``broker_lots`` and optionally purge ``trades``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def migrate(*, run_sync: bool = False, purge_legacy: bool = True) -> dict[str, int]:
    from brokerai.db.client import close_db, get_db
    from brokerai.db.migrations.legacy_trades_to_lots import (
        legacy_trade_to_lot_doc,
        overlay_from_legacy,
        overlay_only_when_state_conflicts,
        pick_best_legacy_per_broker,
    )

    handle = await get_db()

    if run_sync:
        from brokerai.trading.broker.sync import run_broker_sync

        logger.info("Running full broker sync (lots + events)…")
        result = await run_broker_sync(exchange_id="oanda", mode="full", force=True)
        logger.info("Sync result: %s", result.to_dict())

    legacy_trades = await handle.db.trades.find({}, {"_id": 0}).to_list(length=5000)

    stats = {
        "legacy_total": len(legacy_trades),
        "overlay_applied": 0,
        "inserted": 0,
        "skipped_no_broker_id": 0,
        "purged": 0,
    }

    best_by_broker = pick_best_legacy_per_broker(legacy_trades)
    stats["skipped_no_broker_id"] = len(legacy_trades) - len(best_by_broker)

    for broker_id, trade in best_by_broker.items():
        existing = await handle.db.broker_lots.find_one(
            {"exchange_id": "oanda", "broker_lot_id": broker_id},
            {"_id": 0},
        )
        overlay = overlay_from_legacy(trade)

        if existing is not None:
            overlay = overlay_only_when_state_conflicts(existing, trade, overlay)
            now = datetime.now(timezone.utc)
            await handle.db.broker_lots.update_one(
                {"exchange_id": "oanda", "broker_lot_id": broker_id},
                {"$set": {**overlay, "updated_at": now}},
            )
            stats["overlay_applied"] += 1
            logger.info("Overlay applied for broker lot %s (legacy id=%s)", broker_id, trade.get("id"))
            continue

        lot_doc = legacy_trade_to_lot_doc(trade)
        await handle.db.broker_lots.update_one(
            {
                "exchange_id": lot_doc["exchange_id"],
                "account_id": lot_doc["account_id"],
                "broker_lot_id": broker_id,
            },
            {"$set": lot_doc},
            upsert=True,
        )
        stats["inserted"] += 1
        logger.info("Inserted broker lot from legacy trade %s broker_id=%s", trade.get("id"), broker_id)

    if purge_legacy:
        result = await handle.db.trades.delete_many({})
        stats["purged"] = int(result.deleted_count)
        logger.info("Purged %d legacy trade documents", stats["purged"])

    logger.info("Migration complete: %s", stats)
    await close_db()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run full OANDA broker sync before migrating overlays.",
    )
    parser.add_argument(
        "--keep-legacy",
        action="store_true",
        help="Do not delete documents from the legacy trades collection.",
    )
    args = parser.parse_args()

    try:
        asyncio.run(migrate(run_sync=args.sync, purge_legacy=not args.keep_legacy))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
