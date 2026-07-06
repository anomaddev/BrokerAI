from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from brokerai.bots.data_manager.candle_requirements import strategy_params, strategy_timeframe
from brokerai.bots.data_manager.candle_schedule import timeframe_to_duration
from brokerai.bots.data_manager.service import require_data_manager_service
from brokerai.strategies.candles import compute_required_candles, effective_min_candles
from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.tasks.trade_sync import start_trade_sync_task
import brokerai.trading.broker.adapters  # noqa: F401
from brokerai.trading.broker.adapters.oanda import OandaAdapter, lot_from_oanda_trade
from brokerai.trading.broker.reconciliation import reconcile_sync_drift, unconfigured_reconciliation
from brokerai.trading.broker.state import BrokerStateService
from brokerai.db.repositories.broker_lots import DEFAULT_TRADE_CHART_TIMEFRAME
from brokerai.trading.data.candle_cache import OANDA_SOURCE
from brokerai.web.routes.auth import require_auth
from brokerai.web.routes.market_data_helpers import serialize_candle, validate_timeframe

router = APIRouter(prefix="/api/trades", tags=["trades"])
logger = logging.getLogger(__name__)

MANUAL_CLOSE_REASON = "manual_close"
TRADE_CANDLE_PADDING = timedelta(hours=1)
# Single source of truth shared with the anchor computation in broker_lots so the
# chart timeframe and the stored entry_candle_open anchor can never drift apart.
DEFAULT_TRADE_TIMEFRAME = DEFAULT_TRADE_CHART_TIMEFRAME


def _parse_trade_instant(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


async def _resolve_strategy_warmup_bars(trade: dict[str, Any]) -> int:
    """Bars of history before entry required for strategy indicator warmup."""
    strategy_id = str(trade.get("strategy_id") or "").strip()
    if not strategy_id:
        return 0
    strategy = await StrategiesRepository().get_by_id(strategy_id)
    if not strategy:
        return 0

    params = strategy.get("params") or {}
    try:
        normalized = strategy_params(strategy)
        return effective_min_candles(normalized)
    except Exception:
        stored = params.get("min_candles")
        if isinstance(stored, int) and stored > 0:
            return stored
        return compute_required_candles(params)


async def _resolve_trade_timeframe(trade: dict[str, Any]) -> str:
    timeframe = trade.get("timeframe")
    if timeframe:
        return str(timeframe)

    strategy_id = str(trade.get("strategy_id") or "").strip()
    if strategy_id:
        strategy = await StrategiesRepository().get_by_id(strategy_id)
        if strategy:
            tf = strategy_timeframe(strategy)
            if tf:
                return tf

    return DEFAULT_TRADE_TIMEFRAME


def _trade_is_open(trade: dict[str, Any]) -> bool:
    return str(trade.get("state") or "closed") == "open"


def _entry_candle_price_side(trade: dict[str, Any]) -> str:
    """OANDA candle price side matching the *entry* execution price.

    A market buy fills at the ask, a market sell at the bid. Charting the trade
    against mid candles makes the recorded fill float above the high (long) or
    below the low (short) by the half-spread; fetching the execution-side candle
    keeps the entry fill inside the candle range.
    """
    return "B" if str(trade.get("direction") or "").lower() == "short" else "A"


def _accepted_task_response(task_id: str) -> JSONResponse:
    return JSONResponse({"task_id": task_id, "status": "accepted"}, status_code=202)


def _conflict_response(message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "skipped_reason": message}, status_code=409)


@router.get("/reconciliation")
async def get_trade_reconciliation(
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = ExchangeConnectionsRepository()
    oanda = await repo.get_oanda()
    access_token = oanda.get("access_token", "")
    account_id = oanda.get("account_id")
    environment = oanda.get("environment", "practice")

    service = BrokerStateService()
    local_lots = await service.list_lots(state="open", exchange_id="oanda", limit=500)

    if not access_token or not account_id:
        payload = unconfigured_reconciliation()
        payload["local_open_count"] = len(local_lots)
        payload["mongo_open_count"] = len(local_lots)
        payload["unmatched_local"] = local_lots
        payload["unmatched_ledger"] = local_lots
        payload["lot_badges"] = {str(t.get("id", "")): "local_only" for t in local_lots}
        payload["ledger_badges"] = payload["lot_badges"]
        payload["lot_market"] = {}
        payload["ledger_market"] = {}
        return JSONResponse(payload)

    try:
        adapter = OandaAdapter()
        credentials = {"access_token": access_token, "environment": environment}
        raw_lots = await adapter.fetch_open_lots_with_prices(credentials, str(account_id))
        broker_lots = [lot.to_dict() for lot in raw_lots]
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            raise HTTPException(status_code=502, detail="OANDA authorization failed") from exc
        raise HTTPException(status_code=502, detail=f"OANDA returned HTTP {status}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OANDA request failed: {exc}") from exc

    payload = reconcile_sync_drift(local_lots, broker_lots)
    payload["broker_open_count"] = len(broker_lots)
    payload["configured"] = True
    return JSONResponse(payload)


@router.post("/sync")
async def sync_trades(
    force: bool = Query(default=False),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    if force:
        result = await BrokerStateService().sync(exchange_id="oanda", mode="full", force=True)
        return JSONResponse(result.to_dict())
    task_id, error = await start_trade_sync_task()
    if error:
        return _conflict_response(error)
    assert task_id is not None
    return _accepted_task_response(task_id)


@router.get("/exposure")
async def list_instrument_exposure(
    exchange_id: str = Query(default="oanda"),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    service = BrokerStateService()
    rollups = await service.list_instrument_exposure(exchange_id=exchange_id)
    return JSONResponse({"exposure": rollups, "count": len(rollups)})


@router.get("")
async def list_trades(
    _username: str = Depends(require_auth),
    status: str = Query(default="open", pattern="^(open|closed|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None),
    strategy_id: str | None = Query(default=None),
    pair: str | None = Query(default=None),
) -> JSONResponse:
    before_dt: datetime | None = None
    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            before_dt = None

    service = BrokerStateService()
    trades = await service.list_lots(
        state=status,
        strategy_id=strategy_id,
        pair=pair,
        limit=limit,
        before=before_dt,
        exchange_id="oanda",
    )
    return JSONResponse({"trades": trades, "latest": trades[0] if trades else None})


@router.post("/{trade_id}/close")
async def close_trade(
    trade_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    service = BrokerStateService()
    trade = await service.get_lot_by_id(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.get("state") != "open":
        raise HTTPException(status_code=400, detail="Trade is not open")

    updated = await service.close_lot(
        str(trade.get("exchange_id", "oanda")),
        trade_id,
        reason=MANUAL_CLOSE_REASON,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return JSONResponse(updated)


@router.post("/{trade_id}/debug")
async def debug_trade_row(
    trade_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    """Log a clicked trade row to the uvicorn/dev server console for debugging."""
    service = BrokerStateService()
    trade = await service.get_lot_by_id(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")

    broker_lot_id = str(trade.get("broker_lot_id") or "")
    state = str(trade.get("state") or "")
    source = str(trade.get("_source") or "broker_lots")
    units = trade.get("units")
    summary = (
        f"Trade row click id={trade_id} source={source} broker_lot_id={broker_lot_id} "
        f"pair={trade.get('pair')} direction={trade.get('direction')} state={state} units={units}"
    )
    logger.info(summary)
    payload_text = json.dumps(trade, indent=2, default=str)
    logger.info("Trade row click payload:\n%s", payload_text)

    live_on_broker: bool | None = None
    if state == "open" and broker_lot_id:
        repo = ExchangeConnectionsRepository()
        oanda = await repo.get_oanda()
        access_token = str(oanda.get("access_token") or "").strip()
        account_id = str(oanda.get("account_id") or "").strip()
        environment = str(oanda.get("environment") or "practice")
        if access_token and account_id:
            try:
                adapter = OandaAdapter()
                credentials = {"access_token": access_token, "environment": environment}
                live_open = await adapter.fetch_open_lots_with_prices(credentials, account_id)
                live_ids = {lot.broker_lot_id for lot in live_open if lot.broker_lot_id}
                live_on_broker = broker_lot_id in live_ids
                oanda_msg = (
                    f"Trade row click OANDA open check broker_lot_id={broker_lot_id} "
                    f"live_on_broker={live_on_broker} live_ids={sorted(live_ids)}"
                )
                logger.info(oanda_msg)
            except httpx.HTTPError as exc:
                logger.warning("Trade row click OANDA open check failed: %s", exc)

    return JSONResponse(
        {
            "ok": True,
            "trade_id": trade_id,
            "broker_lot_id": broker_lot_id,
            "live_on_broker": live_on_broker,
            "source": source,
        }
    )


@router.get("/{trade_id}/candles")
async def get_trade_candles(
    trade_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    """Fetch OANDA candles for a trade chart (display window + strategy warmup history)."""
    trade = await BrokerStateService().get_lot_by_id(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")

    opened_at = _parse_trade_instant(trade.get("open_time"))
    if opened_at is None:
        raise HTTPException(status_code=400, detail="Trade open time is unavailable")

    pair = str(trade.get("pair") or "").strip()
    if not pair:
        raise HTTPException(status_code=400, detail="Trade pair is unavailable")

    timeframe = await _resolve_trade_timeframe(trade)
    validate_timeframe(timeframe)

    warmup_bars = await _resolve_strategy_warmup_bars(trade)
    bar_duration = timeframe_to_duration(timeframe)

    if _trade_is_open(trade):
        display_until_dt = datetime.now(timezone.utc)
        if warmup_bars > 0:
            # Strategy trade: show from warmup start through live.
            display_since_dt = opened_at - (bar_duration * warmup_bars)
        else:
            # No strategy: default to last 200 candles ending at live.
            display_since_dt = datetime.now(timezone.utc) - (bar_duration * 200)
    else:
        closed_at = _parse_trade_instant(trade.get("closed_at") or trade.get("close_time"))
        if closed_at is None:
            raise HTTPException(status_code=400, detail="Trade close time is unavailable")
        display_until_dt = closed_at + TRADE_CANDLE_PADDING
        display_since_dt = opened_at - TRADE_CANDLE_PADDING

    since_dt = display_since_dt
    if warmup_bars > 0:
        warmup_start = opened_at - (bar_duration * warmup_bars)
        since_dt = min(since_dt, warmup_start)

    # Fetch one extra bar past the display window so the final candle covers exit + 1h.
    until_dt = display_until_dt + bar_duration

    service = require_data_manager_service()
    price_side = _entry_candle_price_side(trade)
    try:
        candles = await service.fetch_candles_from_oanda(
            pair, timeframe, since_dt, until_dt, price=price_side
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Trade candle fetch failed for %s", trade_id)
        raise HTTPException(
            status_code=503,
            detail="Candle data unavailable. Check your OANDA connection in Settings.",
        ) from exc

    if not candles:
        raise HTTPException(
            status_code=503,
            detail="Candle data unavailable. Check your OANDA connection in Settings.",
        )

    return JSONResponse(
        {
            "symbol": pair,
            "timeframe": timeframe,
            "price_side": price_side,
            "source": OANDA_SOURCE,
            "since": since_dt.isoformat(),
            "until": until_dt.isoformat(),
            "display_since": display_since_dt.isoformat(),
            "display_until": display_until_dt.isoformat(),
            "warmup_bars": warmup_bars,
            "candles": [serialize_candle(candle) for candle in candles],
        }
    )


@router.get("/{trade_id}")
async def get_trade(
    trade_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    trade = await BrokerStateService().get_lot_by_id(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return JSONResponse(trade)
