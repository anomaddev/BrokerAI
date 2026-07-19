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
    from brokerai.db.client import init_pg
    from brokerai.db.pg.client import session_scope
    from brokerai.db.pg.models import BrokerLotRow
    from brokerai.db.repositories.broker_lots import _sync_lot_row, fill_candle_anchors
    from brokerai.db.repositories.strategies import StrategiesRepository
    from sqlalchemy import select

    await init_pg()
    async with session_scope() as session:
        rows = (await session.execute(select(BrokerLotRow))).scalars().all()
        lots = [dict(row.doc) for row in rows]

    strategy_cache: dict[str, str | None] = {}
    stats = {"scanned": len(lots), "updated": 0, "skipped": 0}
    strategies_repo = StrategiesRepository()

    for lot in lots:
        strategy_id = str(lot.get("strategy_id") or "")
        strategy_tf: str | None = None
        if strategy_id and strategy_id not in strategy_cache:
            doc = await strategies_repo.get_by_id(strategy_id)
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
            async with session_scope() as session:
                row = await session.get(BrokerLotRow, lot.get("id"))
                if row is None:
                    continue
                doc = dict(row.doc)
                doc.update(updates)
                _sync_lot_row(row, doc)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log updates without writing to Postgres",
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
