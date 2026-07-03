from __future__ import annotations

import logging

from brokerai.db.client import get_db
from brokerai.db.market_data_timeseries import ensure_market_data_timeseries

logger = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    handle = await get_db()
    db = handle.db

    await ensure_market_data_timeseries(db)
    await db.candle_sync_state.create_index(
        [("symbol", 1), ("timeframe", 1), ("source", 1)],
        unique=True,
        name="candle_sync_state_symbol_timeframe_source",
    )
    await db.candle_watch.create_index(
        [("symbol", 1), ("timeframe", 1), ("source", 1), ("requester", 1)],
        unique=True,
        name="candle_watch_symbol_timeframe_source_requester",
    )
    await db.candle_watch.create_index(
        [("source", 1), ("updated_at", -1)],
        name="candle_watch_source_updated_at",
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
    await db.broker_lots.create_index("id", unique=True, name="broker_lots_id")
    await db.broker_lots.create_index(
        [("exchange_id", 1), ("account_id", 1), ("broker_lot_id", 1)],
        unique=True,
        name="broker_lots_exchange_account_lot",
    )
    await db.broker_lots.create_index(
        [("exchange_id", 1), ("strategy_id", 1), ("state", 1), ("open_time", -1)],
        name="broker_lots_exchange_strategy_state_open",
    )
    await db.broker_lots.create_index(
        [("exchange_id", 1), ("symbol", 1), ("state", 1)],
        name="broker_lots_exchange_symbol_state",
    )
    await db.broker_lots.create_index([("state", 1)], name="broker_lots_state")
    await db.broker_events.create_index(
        [("exchange_id", 1), ("account_id", 1), ("broker_event_id", 1)],
        unique=True,
        name="broker_events_exchange_account_event",
    )
    await db.broker_events.create_index(
        [("exchange_id", 1), ("broker_lot_id", 1), ("time", -1)],
        name="broker_events_exchange_lot_time",
    )
    await db.broker_sync_state.create_index(
        [("exchange_id", 1), ("account_id", 1)],
        unique=True,
        name="broker_sync_state_exchange_account",
    )
    await db.oanda_accounts_snapshots.create_index(
        "exchange_id",
        unique=True,
        name="oanda_accounts_snapshots_exchange_id",
    )
    await db.oanda_account_summaries.create_index(
        [("exchange_id", 1), ("account_id", 1), ("synced_at", -1)],
        name="oanda_account_summaries_exchange_account_synced_at",
    )
    await db.strategy_analysis_runs.create_index(
        "id",
        unique=True,
        name="strategy_analysis_runs_id",
    )
    await db.strategy_analysis_runs.create_index(
        [("strategy_id", 1), ("analyzed_at", -1)],
        name="strategy_analysis_runs_strategy_analyzed_at",
    )
    await db.strategy_analysis_runs.create_index(
        [("analyzed_at", -1)],
        name="strategy_analysis_runs_analyzed_at",
    )
    logger.info("MongoDB indexes ensured")
