from __future__ import annotations

import logging

from brokerai.db.client import get_db

logger = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    handle = await get_db()
    db = handle.db

    try:
        await db.market_data.drop_index("market_data_symbol_timeframe_source")
    except Exception:
        pass
    await db.market_data.create_index(
        [("symbol", 1), ("timeframe", 1), ("source", 1), ("time", 1)],
        unique=True,
        name="market_data_symbol_timeframe_source_time",
    )
    await db.market_data.create_index(
        [("symbol", 1), ("timeframe", 1), ("source", 1), ("time", -1)],
        name="market_data_symbol_timeframe_source_time_desc",
    )
    await db.market_data.create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="market_data_expires_at_ttl",
    )
    await db.candle_sync_state.create_index(
        [("symbol", 1), ("timeframe", 1), ("source", 1)],
        unique=True,
        name="candle_sync_state_symbol_timeframe_source",
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
    # Drop legacy index that blocked multiple model capability documents.
    try:
        await db.data_connections.drop_index("data_connections_type")
    except Exception:
        pass
    await db.data_connections.create_index(
        "type",
        unique=True,
        name="data_connections_singleton_type",
        partialFilterExpression={"type": {"$in": ["newsapi", "massive"]}},
    )
    await db.data_connections.create_index(
        [("type", 1), ("model_id", 1)],
        unique=True,
        name="data_connections_model_type_id",
        partialFilterExpression={"type": "model"},
    )
    await db.exchange_connections.create_index(
        "exchange_id",
        unique=True,
        name="exchange_connections_exchange_id",
    )
    await db.research_settings.create_index("id", unique=True, name="research_settings_id")
    await db.asset_settings.create_index(
        "asset_class",
        unique=True,
        name="asset_settings_asset_class",
    )
    await db.strategies.create_index("id", unique=True, name="strategies_id")
    await db.strategies.create_index(
        [("asset_class", 1), ("name", 1)],
        name="strategies_asset_class_name",
    )
    await db.strategies.create_index("preset_id", name="strategies_preset_id")
    await db.bot_activity.create_index([("occurred_at", -1)], name="bot_activity_occurred_at")
    await db.trades.create_index("id", unique=True, name="trades_id")
    await db.trades.create_index(
        [("strategy_id", 1), ("pair", 1), "trade_date"],
        name="trades_strategy_pair_date",
    )
    await db.trades.create_index([("status", 1)], name="trades_status")
    logger.info("MongoDB indexes ensured")
