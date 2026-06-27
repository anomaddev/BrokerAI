from __future__ import annotations

from datetime import datetime

import httpx

from brokerai.market_sessions import TRADING_SESSIONS, session_status

MASSIVE_BASE = "https://api.massive.com"


def _parse_server_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


async def fetch_market_status(api_key: str) -> tuple[bool, dict | str]:
    if not api_key.strip():
        return False, "Massive API key is not configured"

    url = f"{MASSIVE_BASE}/v1/marketstatus/now"
    params = {"apiKey": api_key.strip()}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            if response.status_code in (401, 403):
                return False, "Invalid Massive API key"
            if response.status_code != 200:
                return False, f"Massive returned HTTP {response.status_code}"
            data = response.json()
            if data.get("status") == "ERROR":
                return False, data.get("error", "Massive request failed")
            return True, data
    except httpx.HTTPError as exc:
        return False, f"Massive request failed: {exc}"


def build_session_snapshot(data: dict) -> dict:
    server_time_raw = str(data.get("serverTime") or "")
    if not server_time_raw:
        raise ValueError("Massive response missing serverTime")
    server_time = _parse_server_time(server_time_raw)
    currencies = data.get("currencies") or {}
    exchanges = data.get("exchanges") or {}
    fx_open = str(currencies.get("fx") or "").lower() != "closed"
    nyse_status = str(exchanges.get("nyse") or "") or None

    sessions = []
    for session in TRADING_SESSIONS:
        exchange_status = nyse_status if session.id == "ny" else None
        sessions.append(
            session_status(
                session,
                server_time,
                fx_open=fx_open,
                exchange_status=exchange_status,
            )
        )

    return {
        "enabled": True,
        "server_time": server_time.isoformat(),
        "fx_open": fx_open,
        "market": str(data.get("market") or ""),
        "sessions": sessions,
    }


async def test_massive(api_key: str) -> tuple[bool, str]:
    if not api_key.strip():
        return False, "Massive API key is not configured"

    url = f"{MASSIVE_BASE}/v3/reference/tickers"
    params = {"limit": 1, "apiKey": api_key.strip()}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            if response.status_code in (401, 403):
                return False, "Invalid Massive API key"
            if response.status_code != 200:
                return False, f"Massive returned HTTP {response.status_code}"
            data = response.json()
            if data.get("status") == "ERROR":
                return False, data.get("error", "Massive request failed")
            return True, "Massive connection successful"
    except httpx.HTTPError as exc:
        return False, f"Massive request failed: {exc}"
