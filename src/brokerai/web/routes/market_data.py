from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from brokerai.bots.data_manager.service import require_data_manager_service
from brokerai.db.repositories.candle_sync_state import CandleSyncStateRepository
from brokerai.db.repositories.market_data import MarketDataRepository
from brokerai.trading.data.candle_cache import OANDA_SOURCE
from brokerai.web.routes.auth import require_auth
from brokerai.web.routes.market_data_helpers import (
    CANDLE_LIMIT_DEFAULT,
    CANDLE_LIMIT_MAX,
    CANDLE_LIMIT_MIN,
    WEB_EXPLORE_REQUESTER,
    register_explore_watch,
    resolve_forex_pair,
    serialize_candle,
    validate_timeframe,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-data", tags=["market-data"])

CANDLE_DELTA_MAX = 5
STREAM_POLL_INTERVAL_SECONDS = 1.0
STREAM_WATCH_TOUCH_SECONDS = 60


@router.get("/candles")
async def get_candles(
    symbol: str = Query(..., min_length=3),
    timeframe: str = Query("M15"),
    limit: int = Query(CANDLE_LIMIT_DEFAULT, ge=CANDLE_LIMIT_MIN, le=CANDLE_LIMIT_MAX),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    pair = resolve_forex_pair(symbol)
    validate_timeframe(timeframe)
    await register_explore_watch(pair, timeframe, bar_count=limit)

    service = require_data_manager_service()
    candles = await service.request_candles(
        pair,
        timeframe,
        bar_count=limit,
        source=OANDA_SOURCE,
        requester=WEB_EXPLORE_REQUESTER,
    )

    if not candles:
        raise HTTPException(
            status_code=503,
            detail="Candle data unavailable. Check your OANDA connection in Settings.",
        )

    payload = [serialize_candle(candle) for candle in candles]

    return JSONResponse(
        {
            "symbol": pair,
            "timeframe": timeframe,
            "source": OANDA_SOURCE,
            "candles": payload,
        }
    )


@router.get("/candles/delta")
async def get_candle_delta(
    symbol: str = Query(..., min_length=3),
    timeframe: str = Query("M15"),
    after: str = Query(..., min_length=10),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    pair = resolve_forex_pair(symbol)
    validate_timeframe(timeframe)

    repo = MarketDataRepository()
    candles = await repo.find_candles_after(
        pair,
        timeframe,
        OANDA_SOURCE,
        after,
        limit=CANDLE_DELTA_MAX,
    )
    latest_time = candles[-1]["time"] if candles else after

    return JSONResponse(
        {
            "symbol": pair,
            "timeframe": timeframe,
            "source": OANDA_SOURCE,
            "candles": [serialize_candle(candle) for candle in candles],
            "latest_time": latest_time,
        }
    )


@router.get("/stream")
async def stream_candle_revisions(
    request: Request,
    symbol: str = Query(..., min_length=3),
    timeframe: str = Query("M15"),
    bar_count: int = Query(CANDLE_LIMIT_DEFAULT, ge=CANDLE_LIMIT_MIN, le=CANDLE_LIMIT_MAX),
    _username: str = Depends(require_auth),
) -> StreamingResponse:
    pair = resolve_forex_pair(symbol)
    validate_timeframe(timeframe)
    await register_explore_watch(pair, timeframe, bar_count=bar_count)

    async def event_generator():
        sync_repo = CandleSyncStateRepository()
        last_emitted: str | None = None
        seconds_since_touch = 0.0

        initial_state = await sync_repo.get_state(pair, timeframe, OANDA_SOURCE)
        if initial_state and initial_state.get("high_water_time"):
            last_emitted = str(initial_state["high_water_time"])

        while True:
            if await request.is_disconnected():
                break

            try:
                state = await sync_repo.get_state(pair, timeframe, OANDA_SOURCE)
                latest_time = state.get("high_water_time") if state else None
                if latest_time and latest_time != last_emitted:
                    last_emitted = str(latest_time)
                    payload: dict[str, Any] = {
                        "type": "candle_updated",
                        "symbol": pair,
                        "timeframe": timeframe,
                        "latest_time": last_emitted,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

                seconds_since_touch += STREAM_POLL_INTERVAL_SECONDS
                if seconds_since_touch >= STREAM_WATCH_TOUCH_SECONDS:
                    await register_explore_watch(pair, timeframe, bar_count=bar_count)
                    seconds_since_touch = 0.0
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Candle stream error for %s %s",
                    pair,
                    timeframe,
                )

            yield ": ping\n\n"
            await asyncio.sleep(STREAM_POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
