from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.db.repositories.trades import TradesRepository
from brokerai.integrations.oanda import close_broker_trade, get_broker_open_trades_snapshot
from brokerai.trading.trade_reconciliation import reconcile_open_trades, unconfigured_reconciliation
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/trades", tags=["trades"])

MANUAL_CLOSE_REASON = "manual_close"


@router.get("/reconciliation")
async def get_trade_reconciliation(
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = ExchangeConnectionsRepository()
    oanda = await repo.get_oanda()
    access_token = oanda.get("access_token", "")
    account_id = oanda.get("account_id")
    environment = oanda.get("environment", "practice")

    ledger_trades = await TradesRepository().list_trades(status="open", limit=500)

    if not access_token or not account_id:
        payload = unconfigured_reconciliation()
        payload["mongo_open_count"] = len(ledger_trades)
        payload["unmatched_ledger"] = ledger_trades
        payload["ledger_badges"] = {
            str(t.get("id", "")): "ledger_only" for t in ledger_trades
        }
        payload["ledger_market"] = {}
        return JSONResponse(payload)

    try:
        snapshot = await get_broker_open_trades_snapshot(access_token, environment, account_id)
        broker_trades = snapshot["trades"]
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            raise HTTPException(status_code=502, detail="OANDA authorization failed") from exc
        raise HTTPException(status_code=502, detail=f"OANDA returned HTTP {status}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OANDA request failed: {exc}") from exc

    payload = reconcile_open_trades(ledger_trades, broker_trades)
    payload["broker_open_count"] = snapshot["open_trade_count"]
    payload["configured"] = True
    return JSONResponse(payload)


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

    repo = TradesRepository()
    trades = await repo.list_trades(
        status=status,
        strategy_id=strategy_id,
        pair=pair,
        limit=limit,
        before=before_dt,
    )
    return JSONResponse({"trades": trades, "latest": trades[0] if trades else None})


@router.post("/{trade_id}/close")
async def close_trade(
    trade_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = TradesRepository()
    trade = await repo.get_by_id(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.get("status") != "open":
        raise HTTPException(status_code=400, detail="Trade is not open")

    close_metadata: dict[str, Any] = {}
    broker_order_id = trade.get("broker_order_id")
    if broker_order_id:
        oanda = await ExchangeConnectionsRepository().get_oanda()
        access_token = oanda.get("access_token", "")
        account_id = oanda.get("account_id")
        environment = oanda.get("environment", "practice")
        if access_token and account_id:
            try:
                close_metadata["broker_close"] = await close_broker_trade(
                    access_token,
                    environment,
                    str(account_id),
                    str(broker_order_id),
                )
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (401, 403):
                    raise HTTPException(status_code=502, detail="OANDA authorization failed") from exc
                raise HTTPException(status_code=502, detail=f"OANDA returned HTTP {status}") from exc
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=f"OANDA request failed: {exc}") from exc
        else:
            close_metadata["broker_skipped"] = "oanda_not_configured"

    await repo.close_trade(trade_id, reason=MANUAL_CLOSE_REASON, metadata=close_metadata)
    updated = await repo.get_by_id(trade_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return JSONResponse(updated)


@router.get("/{trade_id}")
async def get_trade(
    trade_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    trade = await TradesRepository().get_by_id(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return JSONResponse(trade)
