from __future__ import annotations

import logging

from brokerai.db.client import get_db
from brokerai.db.market_data_timeseries import ensure_market_data_timeseries

logger = logging.getLogger(__name__)


async def _dedupe_strategy_analysis_runs(db) -> None:
    """Collapse duplicate rows for the same strategy, pair, candle, and purpose."""
    await db.strategy_analysis_runs.update_many(
        {"analysis_purpose": {"$exists": False}},
        {"$set": {"analysis_purpose": "entry"}},
    )
    pipeline = [
        {
            "$match": {
                "candle_time": {"$type": "date"},
                "strategy_id": {"$type": "string"},
                "pair": {"$type": "string"},
            }
        },
        {
            "$group": {
                "_id": {
                    "strategy_id": "$strategy_id",
                    "pair": "$pair",
                    "candle_time": "$candle_time",
                    "analysis_purpose": {"$ifNull": ["$analysis_purpose", "entry"]},
                    "trade_id": {"$ifNull": ["$trade_id", None]},
                },
                "docs": {
                    "$push": {
                        "id": "$id",
                        "run_type": "$run_type",
                        "execution": "$execution",
                        "analyzed_at": "$analyzed_at",
                    }
                },
                "count": {"$sum": 1},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
    ]
    duplicate_groups = await db.strategy_analysis_runs.aggregate(pipeline).to_list(length=None)
    if not duplicate_groups:
        return

    for group in duplicate_groups:
        docs = group["docs"]

        def _rank(doc: dict) -> tuple:
            execution = doc.get("execution")
            has_execution = 1 if execution else 0
            is_manual = 1 if doc.get("run_type") == "manual" else 0
            analyzed_at = doc.get("analyzed_at")
            return (is_manual, has_execution, analyzed_at)

        keeper = max(docs, key=_rank)
        keeper_id = keeper["id"]
        for doc in docs:
            run_id = doc["id"]
            if run_id == keeper_id:
                continue
            execution = doc.get("execution")
            if execution and not keeper.get("execution"):
                await db.strategy_analysis_runs.update_one(
                    {"id": keeper_id},
                    {"$set": {"execution": execution}},
                )
                keeper["execution"] = execution
            if doc.get("run_type") == "manual":
                await db.strategy_analysis_runs.update_one(
                    {"id": keeper_id},
                    {"$set": {"run_type": "manual"}},
                )
            await db.strategy_analysis_runs.delete_one({"id": run_id})
            logger.info(
                "Removed duplicate strategy analysis run %s (kept %s for %s %s)",
                run_id,
                keeper_id,
                group["_id"]["pair"],
                group["_id"]["candle_time"],
            )


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
    await db.cost_ledger.create_index([("occurred_at", -1)], name="cost_ledger_occurred_at")
    await db.cost_ledger.create_index("id", unique=True, name="cost_ledger_id")
    await db.cost_ledger.create_index(
        [("category", 1), ("occurred_at", -1)],
        name="cost_ledger_category_occurred_at",
    )
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
    await db.broker_events.create_index(
        [("exchange_id", 1), ("account_id", 1), ("broker_order_id", 1), ("time", -1)],
        name="broker_events_exchange_account_order_time",
    )
    await db.broker_events.create_index(
        [("retention_expires_at", 1)],
        name="broker_events_retention_expires_at",
        expireAfterSeconds=0,
        partialFilterExpression={"retention_expires_at": {"$exists": True}},
    )
    await db.instrument_exposure.create_index(
        [("exchange_id", 1), ("account_id", 1), ("symbol", 1), ("direction", 1)],
        unique=True,
        name="instrument_exposure_exchange_account_symbol_direction",
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
    await _dedupe_strategy_analysis_runs(db)
    # Drop legacy unique index if present (pre-analysis_purpose schema).
    try:
        await db.strategy_analysis_runs.drop_index("strategy_analysis_runs_strategy_pair_candle")
    except Exception:
        pass
    await db.strategy_analysis_runs.create_index(
        [
            ("strategy_id", 1),
            ("pair", 1),
            ("candle_time", 1),
            ("analysis_purpose", 1),
            ("trade_id", 1),
        ],
        unique=True,
        partialFilterExpression={"candle_time": {"$type": "date"}},
        name="strategy_analysis_runs_strategy_pair_candle_purpose",
    )
    await db.config_backups.create_index(
        [("created_at", -1)],
        name="config_backups_created_at",
    )
    await db.config_backups.create_index(
        "id",
        unique=True,
        name="config_backups_id",
    )
    await db.config_backups.create_index(
        [("kind", 1), ("created_at", -1)],
        name="config_backups_kind_created_at",
    )
    await db.backup_settings.create_index(
        "id",
        unique=True,
        name="backup_settings_id",
    )
    logger.info("MongoDB indexes ensured")
