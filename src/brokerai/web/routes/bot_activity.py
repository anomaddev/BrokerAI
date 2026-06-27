from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from brokerai.db.repositories.bot_activity import BotActivityRepository
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/bot", tags=["bot"])


@router.get("/activity")
async def list_bot_activity(
    _username: str = Depends(require_auth),
    limit: int = Query(default=20, ge=1, le=100),
    before: str | None = Query(default=None),
) -> JSONResponse:
    before_dt: datetime | None = None
    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            before_dt = None

    repo = BotActivityRepository()
    events = await repo.list_recent(limit=limit, before=before_dt)
    return JSONResponse({"events": events, "latest": events[0] if events else None})
