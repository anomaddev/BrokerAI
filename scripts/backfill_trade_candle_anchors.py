#!/usr/bin/env python3
"""Backfill ``timeframe``, ``entry_candle_open``, and ``exit_candle_open`` on broker lots."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def backfill(*, dry_run: bool = False) -> dict[str, int]:
    from brokerai.bots.data_manager.candle_requirements import strategy_timeframe
    from brokerai.db.client import close_db, get_db
    from brokerai.db.repositories.broker_lots import fill_candle_anchors

    handle = await get_db()
    lots = await handle.db.broker_lots.find({}, {"_id": 0}).to_list(length=10000)

    strategy_cache: dict[str, str | None] = {}
    stats = {"scanned": len(lots), "updated": 0, "skipped": 0}

    for lot in lots:
        strategy_id = str(lot.get("strategy_id") or "")
        strategy_tf: str | None = None
        if strategy_id and strategy_id not in strategy_cache:
            doc = await handle.db.strategies.find_one(
                {"id": strategy_id},
                {"_id": 0, "timeframe": 1, "params": 1},
            )
            strategy_cache[strategy_id] = strategy_timeframe(doc) if doc else None
        if strategy_id:
            strategy_tf = strategy_cache.get(strategy_id)

        filled = fill_candle_anchors(lot, strategy_timeframe=strategy_tf)
        updates: dict[str, str] = {}
        for field in ("timeframe", "entry_candle_open", "exit_candle_open"):
            if not lot.get(field) and filled.get(field):
                updates[field] = filled[field]

        if not updates:
            stats["skipped"] += 1
            continue

        stats["updated"] += 1
        lot_id = lot.get("id", "?")
        logger.info("Lot %s: %s", lot_id, updates)
        if not dry_run:
            await handle.db.broker_lots.update_one({"id": lot.get("id")}, {"$set": updates})

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log updates without writing to MongoDB",
    )
    args = parser.parse_args()

    async def run() -> int:
        from brokerai.db.client import close_db

        try:
            stats = await backfill(dry_run=args.dry_run)
            logger.info("Done: %s", stats)
            return 0
        finally:
            await close_db()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
