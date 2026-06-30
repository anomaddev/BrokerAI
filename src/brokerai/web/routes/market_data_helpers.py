from __future__ import annotations

from typing import Any

from brokerai.db.repositories.asset_settings import FOREX_PAIR_CATALOG
from brokerai.db.repositories.candle_watch import CandleWatchRepository
from brokerai.integrations.oanda import OANDA_GRANULARITY_BY_TIMEFRAME
from brokerai.trading.data.candle_cache import OANDA_SOURCE

WEB_EXPLORE_REQUESTER = "web_explore"

CANDLE_LIMIT_MIN = 50
CANDLE_LIMIT_MAX = 2000
CANDLE_LIMIT_DEFAULT = 200


def resolve_forex_pair(symbol: str) -> str:
    from fastapi import HTTPException

    trimmed = symbol.strip()
    if trimmed in FOREX_PAIR_CATALOG:
        return trimmed
    upper = trimmed.upper()
    for pair in FOREX_PAIR_CATALOG:
        if pair.upper() == upper:
            return pair
    raise HTTPException(status_code=400, detail=f"Unknown forex pair: {symbol}")


def serialize_candle(candle: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": candle["time"],
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
        "volume": candle.get("volume", 0),
    }


def validate_timeframe(timeframe: str) -> None:
    from fastapi import HTTPException

    if timeframe not in OANDA_GRANULARITY_BY_TIMEFRAME:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")


async def register_explore_watch(
    symbol: str,
    timeframe: str,
    *,
    bar_count: int,
) -> None:
    repo = CandleWatchRepository()
    await repo.upsert_watch(
        symbol,
        timeframe,
        OANDA_SOURCE,
        WEB_EXPLORE_REQUESTER,
        bar_count=bar_count,
    )
