"""OHLCV candle document helpers (Postgres ``market_candles`` table uses these shapes).

Document field names ``ts`` and ``meta`` are preserved in helpers so repository
callers keep receiving the same candle dicts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

COLLECTION = "market_data"
TIME_FIELD = "ts"
META_FIELD = "meta"


def series_meta(symbol: str, timeframe: str, source: str) -> dict[str, str]:
    """Return the meta subdocument identifying one candle series."""
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "source": source,
    }


def meta_query_filter(symbol: str, timeframe: str, source: str) -> dict[str, str]:
    """Series key filter using ``meta.*`` field names."""
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


def timeseries_document_to_candle(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize a time-series measurement document for callers."""
    meta = document.get(META_FIELD)
    if not isinstance(meta, dict):
        symbol = str(document.get("symbol", ""))
        timeframe = str(document.get("timeframe", ""))
        source = str(document.get("source", ""))
        meta = series_meta(symbol, timeframe, source)

    symbol = str(meta.get("symbol", ""))
    timeframe = str(meta.get("timeframe", ""))
    source = str(meta.get("source", ""))

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


async def ensure_market_data_timeseries(db: Any = None) -> None:
    """No-op: ``ensure_schema`` owns ``market_candles``."""
    del db


async def purge_expired_market_candles(session: Any) -> int:
    """Delete ephemeral candles whose ``expires_at`` is in the past (idempotent)."""
    from sqlalchemy import delete

    from brokerai.db.pg.models import MarketCandle

    now = datetime.now(timezone.utc)
    result = await session.execute(
        delete(MarketCandle).where(
            MarketCandle.expires_at.is_not(None),
            MarketCandle.expires_at <= now,
        )
    )
    deleted = int(result.rowcount or 0)
    if deleted:
        logger.info("Purged %d expired market_data candles", deleted)
    return deleted
