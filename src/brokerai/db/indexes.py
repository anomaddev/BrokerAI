from __future__ import annotations

import logging

from brokerai.db.client import get_db

logger = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    handle = await get_db()
    db = handle.db

    await db.market_data.create_index(
        [("symbol", 1), ("timeframe", 1), ("source", 1)],
        unique=True,
        name="market_data_symbol_timeframe_source",
    )
    await db.market_data.create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="market_data_expires_at_ttl",
    )
    await db.research_cache.create_index(
        [("date", 1), ("category", 1)],
        unique=True,
        name="research_cache_date_category",
    )
    await db.analysis_results.create_index(
        [("symbol", 1), ("created_at", -1)],
        name="analysis_results_symbol_created_at",
    )
    await db.ai_models.create_index("id", unique=True, name="ai_models_id")
    await db.data_connections.create_index("type", unique=True, name="data_connections_type")
    await db.research_settings.create_index("id", unique=True, name="research_settings_id")
    await db.asset_settings.create_index(
        "asset_class",
        unique=True,
        name="asset_settings_asset_class",
    )
    logger.info("MongoDB indexes ensured")
