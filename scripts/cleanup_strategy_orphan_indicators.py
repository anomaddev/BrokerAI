#!/usr/bin/env python3
"""Remove orphan ``fast``/``slow`` indicators left by pre-replace indicator merges.

When builders saved component-id EMAs (``ema_*``), ``merge_with_defaults`` used to
union them with preset defaults, leaving unused ``fast``/``slow`` keys in
``brokerai.strategies.doc.params.indicators``.

Usage:
  ./venv/bin/python scripts/cleanup_strategy_orphan_indicators.py --dry-run
  ./venv/bin/python scripts/cleanup_strategy_orphan_indicators.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cleanup(*, dry_run: bool = False) -> dict[str, int]:
    from sqlalchemy import select

    from brokerai.db.client import init_pg
    from brokerai.db.pg.client import session_scope
    from brokerai.db.pg.models import StrategyRow
    from brokerai.db.repositories.strategies import _sync_row_columns
    from brokerai.strategies.params.cleanup import prune_orphan_legacy_indicators

    await init_pg()
    async with session_scope() as session:
        rows = (await session.execute(select(StrategyRow))).scalars().all()
        snapshots = [(row.id, dict(row.doc)) for row in rows]

    stats = {"scanned": len(snapshots), "updated": 0, "skipped": 0}

    for strategy_id, doc in snapshots:
        params = doc.get("params")
        if not isinstance(params, dict):
            stats["skipped"] += 1
            continue

        cleaned = prune_orphan_legacy_indicators(params)
        if cleaned is None:
            stats["skipped"] += 1
            continue

        before = sorted((params.get("indicators") or {}).keys())
        after = sorted((cleaned.get("indicators") or {}).keys())
        stats["updated"] += 1
        logger.info("Strategy %s (%s): indicators %s -> %s", strategy_id, doc.get("name"), before, after)

        if dry_run:
            continue

        async with session_scope() as session:
            row = await session.get(StrategyRow, strategy_id)
            if row is None:
                continue
            updated_doc = dict(row.doc)
            updated_doc["params"] = cleaned
            _sync_row_columns(row, updated_doc)

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
            stats = await cleanup(dry_run=args.dry_run)
            logger.info("Done: %s", stats)
            return 0
        finally:
            await close_db()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
