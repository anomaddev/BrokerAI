from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from brokerai.db.repositories.data_connections import DataConnectionsRepository
from brokerai.integrations.massive_cache import (
    build_cached_session_snapshot,
    fetch_market_status_cached,
)
from brokerai.market_sessions import TRADING_SESSIONS, session_hours_label
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/market-status", tags=["market-status"])


@router.get("/definitions")
async def get_session_definitions(_username: str = Depends(require_auth)) -> JSONResponse:
    sessions = [
        {
            "id": session.id,
            "name": session.name,
            "hours": session_hours_label(session),
            "start_hour": session.start_hour,
            "start_minute": session.start_minute,
            "end_hour": session.end_hour,
            "end_minute": session.end_minute,
        }
        for session in TRADING_SESSIONS
    ]
    return JSONResponse({"sessions": sessions})


@router.get("")
async def get_market_status(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = DataConnectionsRepository()
    massive = await repo.get_massive()
    api_key = str(massive.get("api_key") or "")
    connection_enabled = bool(massive.get("enabled"))
    configured = bool(api_key.strip())

    if not configured:
        return JSONResponse(
            {
                "enabled": False,
                "connection_enabled": connection_enabled,
                "configured": False,
                "sessions": [],
            }
        )

    ok, result = await fetch_market_status_cached(api_key)
    if not ok:
        return JSONResponse(
            {
                "enabled": True,
                "available": False,
                "connection_enabled": connection_enabled,
                "configured": True,
                "error": str(result),
                "sessions": [],
            }
        )

    try:
        payload = build_cached_session_snapshot(result)
    except (ValueError, TypeError) as exc:
        return JSONResponse(
            {
                "enabled": True,
                "available": False,
                "connection_enabled": connection_enabled,
                "configured": True,
                "error": str(exc),
                "sessions": [],
            }
        )

    payload["connection_enabled"] = connection_enabled
    payload["configured"] = True
    return JSONResponse(payload)
