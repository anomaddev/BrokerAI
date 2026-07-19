from __future__ import annotations

import logging

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.schema import ensure_schema
from brokerai.db.market_data_timeseries import purge_expired_market_candles

logger = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    """Ensure Postgres schema exists, then purge expired ephemeral candles."""
    await ensure_schema()
    async with session_scope() as session:
        await purge_expired_market_candles(session)
    try:
        from brokerai.db.repositories.ai_models import AiModelsRepository

        deleted = await AiModelsRepository().dedupe_by_type()
        if deleted:
            logger.info("Deduped %s duplicate AI API source(s)", len(deleted))
    except Exception:
        logger.exception("Failed to dedupe AI API sources")
    logger.debug("Postgres index ensure complete")
