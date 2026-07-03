from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.db.repositories.oanda_account_snapshots import OandaAccountSnapshotsRepository
from brokerai.integrations.oanda import test_connection as oanda_test_connection
from brokerai.trading.oanda_account_sync import get_cached_oanda_account_summary, run_oanda_account_sync
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


@router.get("/oanda/accounts")
async def get_oanda_accounts(_username: str = Depends(require_auth)) -> JSONResponse:
    """Return the most recently synced OANDA account list from MongoDB."""
    repo = ExchangeConnectionsRepository()
    oanda = await repo.get_oanda()
    if not oanda.get("access_token"):
        raise HTTPException(status_code=400, detail="OANDA is not connected")

    snapshots_repo = OandaAccountSnapshotsRepository()
    doc = await snapshots_repo.get_latest_accounts()
    if doc is None:
        sync = await run_oanda_account_sync(force=True)
        if sync.accounts_count == 0 and sync.skipped_reason == "not_configured":
            raise HTTPException(status_code=400, detail="OANDA is not connected")
        doc = await snapshots_repo.get_latest_accounts()
        if doc is None:
            raise HTTPException(status_code=503, detail="OANDA account list not synced yet")

    synced_at = doc.get("synced_at")
    return JSONResponse(
        {
            "accounts": doc.get("accounts") or [],
            "environment": doc.get("environment"),
            "synced_at": synced_at.isoformat() if isinstance(synced_at, datetime) else synced_at,
        }
    )


@router.get("/oanda/account-summary")
async def get_oanda_account_summary(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = ExchangeConnectionsRepository()
    oanda = await repo.get_oanda()
    access_token = oanda.get("access_token", "")
    account_id = oanda.get("account_id")

    if not access_token or not account_id:
        raise HTTPException(status_code=400, detail="OANDA is not connected")

    summary = await get_cached_oanda_account_summary(force_sync_if_missing=True)
    if summary is None:
        raise HTTPException(
            status_code=503,
            detail="OANDA account summary not synced yet; try again shortly",
        )

    return JSONResponse(summary)


@router.get("/oanda/account-summary/history")
async def get_oanda_account_summary_history(
    _username: str = Depends(require_auth),
    since: str | None = Query(default=None, description="ISO-8601 UTC lower bound (inclusive)"),
    until: str | None = Query(default=None, description="ISO-8601 UTC upper bound (inclusive)"),
    limit: int = Query(default=2000, ge=1, le=10_000),
) -> JSONResponse:
    """Return time-series account summary snapshots for charting."""
    repo = ExchangeConnectionsRepository()
    oanda = await repo.get_oanda()
    account_id = oanda.get("account_id")
    if not oanda.get("access_token") or not account_id:
        raise HTTPException(status_code=400, detail="OANDA is not connected")

    since_dt = _parse_iso_datetime(since)
    until_dt = _parse_iso_datetime(until)

    snapshots_repo = OandaAccountSnapshotsRepository()
    rows = await snapshots_repo.list_summary_history(
        account_id=str(account_id),
        since=since_dt,
        until=until_dt,
        limit=limit,
    )
    points = [snapshots_repo.public_summary(row) for row in rows]
    return JSONResponse({"account_id": account_id, "points": points})


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid datetime: {raw}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
