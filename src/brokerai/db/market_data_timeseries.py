"""MongoDB Time Series setup and document helpers for OHLCV candles.

OANDA candle cache uses a time-series ``market_data`` collection:

- ``ts`` (timeField) — UTC ``datetime`` for range scans and bucket layout
- ``meta`` (metaField) — ``symbol``, ``timeframe``, ``source`` series key
- ``time`` — OANDA ISO string preserved for API compatibility

Time-series collections do not support updates; upserts delete matching
``(meta, ts)`` rows then insert fresh measurements (idempotent sync).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

COLLECTION = "market_data"
MIGRATION_COLLECTION = "market_data_timeseries_migration"
TIME_FIELD = "ts"
META_FIELD = "meta"
MIGRATION_BATCH_SIZE = 1000


def series_meta(symbol: str, timeframe: str, source: str) -> dict[str, str]:
    """Return the meta subdocument identifying one candle series."""
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "source": source,
    }


def meta_query_filter(symbol: str, timeframe: str, source: str) -> dict[str, str]:
    """MongoDB filter matching one series inside a time-series collection."""
    return {
        f"{META_FIELD}.symbol": symbol,
        f"{META_FIELD}.timeframe": timeframe,
        f"{META_FIELD}.source": source,
    }


def candle_open_time_to_datetime(raw: Any) -> datetime | None:
    """Parse a candle open time (OANDA string or datetime) to UTC."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)
    text = str(raw).strip()
    if not text:
        return None
    from brokerai.trading.data.time_utils import parse_oanda_time

    return parse_oanda_time(text)


def candle_open_time_to_string(raw: Any, *, ts: datetime | None = None) -> str:
    """Return the canonical OANDA open-time string for a candle."""
    from brokerai.trading.data.time_utils import format_oanda_time

    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if ts is not None:
        return format_oanda_time(ts)
    if isinstance(raw, datetime):
        return format_oanda_time(raw)
    return str(raw)


def candle_to_timeseries_document(
    symbol: str,
    timeframe: str,
    source: str,
    candle: dict[str, Any],
    *,
    fetched_at: datetime,
    expires_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Build a time-series measurement document from a normalized OHLCV candle."""
    ts = candle_open_time_to_datetime(candle.get("time"))
    if ts is None:
        return None

    document: dict[str, Any] = {
        TIME_FIELD: ts,
        META_FIELD: series_meta(symbol, timeframe, source),
        "time": candle_open_time_to_string(candle.get("time"), ts=ts),
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
        "volume": candle.get("volume", 0),
        "fetched_at": fetched_at,
    }
    if candle.get("sessions") is not None:
        document["sessions"] = candle["sessions"]
    if candle.get("trading_day_et") is not None:
        document["trading_day_et"] = candle["trading_day_et"]
    if expires_at is not None:
        document["expires_at"] = expires_at
    return document


def flat_document_to_timeseries(document: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a legacy flat ``market_data`` document to time-series shape."""
    symbol = document.get("symbol")
    timeframe = document.get("timeframe")
    source = document.get("source")
    if not symbol or not timeframe or not source:
        return None

    ts = candle_open_time_to_datetime(document.get("time"))
    if ts is None:
        return None

    converted: dict[str, Any] = {
        TIME_FIELD: ts,
        META_FIELD: series_meta(str(symbol), str(timeframe), str(source)),
        "time": candle_open_time_to_string(document.get("time"), ts=ts),
        "open": document["open"],
        "high": document["high"],
        "low": document["low"],
        "close": document["close"],
        "volume": document.get("volume", 0),
        "fetched_at": document.get("fetched_at") or datetime.now(timezone.utc),
    }
    if document.get("sessions") is not None:
        converted["sessions"] = document["sessions"]
    if document.get("trading_day_et") is not None:
        converted["trading_day_et"] = document["trading_day_et"]
    if document.get("expires_at") is not None:
        converted["expires_at"] = document["expires_at"]
    return converted


def timeseries_document_to_candle(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize a stored document (time-series or legacy flat) for callers."""
    meta = document.get(META_FIELD)
    if isinstance(meta, dict):
        symbol = str(meta.get("symbol", ""))
        timeframe = str(meta.get("timeframe", ""))
        source = str(meta.get("source", ""))
    else:
        symbol = str(document.get("symbol", ""))
        timeframe = str(document.get("timeframe", ""))
        source = str(document.get("source", ""))

    ts = document.get(TIME_FIELD)
    if ts is None and document.get("time") is not None:
        ts = candle_open_time_to_datetime(document.get("time"))

    candle: dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "source": source,
        "time": candle_open_time_to_string(document.get("time"), ts=ts if isinstance(ts, datetime) else None),
        "open": document["open"],
        "high": document["high"],
        "low": document["low"],
        "close": document["close"],
        "volume": document.get("volume", 0),
    }
    if document.get("fetched_at") is not None:
        candle["fetched_at"] = document["fetched_at"]
    if document.get("sessions") is not None:
        candle["sessions"] = document["sessions"]
    if document.get("trading_day_et") is not None:
        candle["trading_day_et"] = document["trading_day_et"]
    if document.get("expires_at") is not None:
        candle["expires_at"] = document["expires_at"]
    return candle


def candle_open_time_from_document(document: dict[str, Any]) -> str | None:
    """Extract the OANDA open-time string from a full or time-only projection."""
    raw_time = document.get("time")
    if raw_time is not None and str(raw_time).strip():
        return str(raw_time).strip()

    ts = document.get(TIME_FIELD)
    if isinstance(ts, datetime):
        return candle_open_time_to_string(None, ts=ts)
    return None


async def collection_is_timeseries(db: Any, name: str) -> bool:
    """Return True when *name* exists and is a time-series collection."""
    cursor = db.list_collections(filter={"name": name})
    if hasattr(cursor, "__await__"):
        cursor = await cursor
    async for spec in cursor:
        options = spec.get("options") or {}
        return "timeseries" in options
    return False


async def create_timeseries_collection(db: Any, name: str) -> None:
    """Create an empty OHLCV time-series collection."""
    await db.create_collection(
        name,
        timeseries={
            "timeField": TIME_FIELD,
            "metaField": META_FIELD,
            "granularity": "minutes",
        },
    )
    logger.info("Created MongoDB time-series collection %s", name)


async def _migrate_flat_collection(db: Any, *, source_name: str, target_name: str) -> int:
    """Copy legacy flat candles into a time-series collection."""
    source = db[source_name]
    target = db[target_name]
    batch: list[dict[str, Any]] = []
    migrated = 0

    async for document in source.find({}):
        converted = flat_document_to_timeseries(document)
        if converted is None:
            continue
        batch.append(converted)
        if len(batch) >= MIGRATION_BATCH_SIZE:
            await target.insert_many(batch, ordered=False)
            migrated += len(batch)
            batch = []

    if batch:
        await target.insert_many(batch, ordered=False)
        migrated += len(batch)

    return migrated


async def ensure_market_data_timeseries(db: Any) -> None:
    """Ensure ``market_data`` is a time-series collection (migrate legacy data once)."""
    names = await db.list_collection_names()

    if COLLECTION not in names:
        await create_timeseries_collection(db, COLLECTION)
        await _ensure_ttl_index(db[COLLECTION])
        return

    if await collection_is_timeseries(db, COLLECTION):
        await _drop_legacy_market_data_indexes(db)
        await _ensure_ttl_index(db[COLLECTION])
        return

    logger.info("Migrating flat market_data collection to MongoDB time series")
    if MIGRATION_COLLECTION in names:
        await db[MIGRATION_COLLECTION].drop()

    await create_timeseries_collection(db, MIGRATION_COLLECTION)
    migrated = await _migrate_flat_collection(
        db,
        source_name=COLLECTION,
        target_name=MIGRATION_COLLECTION,
    )
    await db[COLLECTION].drop()
    await db[MIGRATION_COLLECTION].rename(COLLECTION)
    await _ensure_ttl_index(db[COLLECTION])
    logger.info("Migrated %d market_data candles to time series", migrated)


async def _drop_legacy_market_data_indexes(db: Any) -> None:
    """Remove unique/compound indexes from the pre-time-series schema."""
    for index_name in (
        "market_data_symbol_timeframe_source",
        "market_data_symbol_timeframe_source_time",
        "market_data_symbol_timeframe_source_time_desc",
    ):
        try:
            await db[COLLECTION].drop_index(index_name)
        except Exception:
            pass


async def _ensure_ttl_index(collection: Any) -> None:
    """TTL index for ephemeral explore/watch candles (unchanged semantics)."""
    try:
        await collection.create_index(
            "expires_at",
            expireAfterSeconds=0,
            name="market_data_expires_at_ttl",
        )
    except Exception as exc:
        message = str(exc).lower()
        if "already exists" in message or "duplicate key" in message:
            return
        raise
