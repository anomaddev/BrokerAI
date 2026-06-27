from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.integrations.oanda import get_account_summary as oanda_get_account_summary
from brokerai.integrations.oanda import test_connection as oanda_test_connection
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/settings/exchanges", tags=["settings-exchanges"])


class OandaSaveBody(BaseModel):
    access_token: str = Field(default="", max_length=500)
    environment: str = Field(default="practice", pattern="^(practice|live)$")
    account_id: str = Field(min_length=1, max_length=120)


class OandaTestBody(BaseModel):
    access_token: str = Field(default="", max_length=500)
    environment: str = Field(default="practice", pattern="^(practice|live)$")
    account_id: str = Field(default="", max_length=120)


@router.get("")
async def list_exchange_connections(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = ExchangeConnectionsRepository()
    oanda = await repo.get_oanda()
    return JSONResponse({"oanda": repo.public_oanda(oanda)})


@router.get("/oanda")
async def get_oanda_connection(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = ExchangeConnectionsRepository()
    oanda = await repo.get_oanda()
    return JSONResponse(repo.public_oanda(oanda))


@router.put("/oanda")
async def save_oanda_connection(
    body: OandaSaveBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = ExchangeConnectionsRepository()
    existing = await repo.get_oanda()
    access_token = body.access_token.strip() or existing.get("access_token", "")
    if not access_token:
        raise HTTPException(status_code=400, detail="An access token is required")

    doc = await repo.save_oanda(
        access_token=access_token,
        environment=body.environment,
        account_id=body.account_id,
    )
    return JSONResponse(repo.public_oanda(doc))


@router.delete("/oanda")
async def delete_oanda_connection(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = ExchangeConnectionsRepository()
    await repo.delete_oanda()
    return JSONResponse({"ok": True})


@router.post("/oanda/test-connection")
async def test_oanda_connection(
    body: OandaTestBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = ExchangeConnectionsRepository()
    access_token = body.access_token.strip()
    if not access_token:
        existing = await repo.get_oanda()
        access_token = existing.get("access_token", "")

    ok, message, accounts = await oanda_test_connection(
        access_token,
        body.environment,
        body.account_id or None,
    )
    return JSONResponse({"ok": ok, "message": message, "accounts": accounts})


@router.get("/oanda/account-summary")
async def get_oanda_account_summary(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = ExchangeConnectionsRepository()
    oanda = await repo.get_oanda()
    access_token = oanda.get("access_token", "")
    account_id = oanda.get("account_id")
    environment = oanda.get("environment", "practice")

    if not access_token or not account_id:
        raise HTTPException(status_code=400, detail="OANDA is not connected")

    try:
        summary = await oanda_get_account_summary(access_token, environment, account_id)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            raise HTTPException(status_code=502, detail="Invalid OANDA access token") from exc
        if status == 403:
            raise HTTPException(
                status_code=502,
                detail="Token is not authorized for this environment",
            ) from exc
        raise HTTPException(status_code=502, detail=f"OANDA returned HTTP {status}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OANDA request failed: {exc}") from exc

    return JSONResponse(summary)


@router.post("/oanda/test")
async def test_saved_oanda_connection(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = ExchangeConnectionsRepository()
    oanda = await repo.get_oanda()
    ok, message, accounts = await oanda_test_connection(
        oanda.get("access_token", ""),
        oanda.get("environment", "practice"),
        oanda.get("account_id"),
    )
    return JSONResponse({"ok": ok, "message": message, "accounts": accounts})
