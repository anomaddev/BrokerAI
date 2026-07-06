from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from brokerai.db.repositories.cost_ledger import CostLedgerRepository
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/cost-ledger", tags=["cost-ledger"])


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.get("")
async def list_cost_ledger(
    _username: str = Depends(require_auth),
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None),
    category: str | None = Query(default=None),
) -> JSONResponse:
    before_dt = _parse_iso_datetime(before)
    repo = CostLedgerRepository()
    items = await repo.list_recent(category=category, limit=limit, before=before_dt)
    return JSONResponse({"items": items, "latest": items[0] if items else None})


@router.get("/summary")
async def summarize_cost_ledger(
    _username: str = Depends(require_auth),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    category: str | None = Query(default=None),
    billable_only: bool = Query(default=True),
) -> JSONResponse:
    since_dt = _parse_iso_datetime(since)
    until_dt = _parse_iso_datetime(until)
    if until_dt is None:
        until_dt = datetime.now(timezone.utc)

    repo = CostLedgerRepository()
    summary = await repo.summarize(
        since=since_dt,
        until=until_dt,
        category=category,
        billable_only=billable_only,
    )
    return JSONResponse(summary)
