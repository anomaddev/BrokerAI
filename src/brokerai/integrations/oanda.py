from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OANDA_ENVIRONMENTS = ("practice", "live")

_BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


def base_url(environment: str) -> str:
    return _BASE_URLS.get(environment, _BASE_URLS["practice"])


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token.strip()}"}


async def list_accounts(access_token: str, environment: str) -> list[dict[str, Any]]:
    """Return the sub-accounts accessible with the given token.

    Raises httpx.HTTPError on transport failures and httpx.HTTPStatusError on
    non-2xx responses so callers can translate them into user-facing messages.
    """
    url = f"{base_url(environment)}/v3/accounts"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=_auth_headers(access_token))
        response.raise_for_status()
        data = response.json()
    accounts = data.get("accounts") or []
    return [
        {"id": acc.get("id"), "tags": acc.get("tags") or []}
        for acc in accounts
        if acc.get("id")
    ]


async def get_account_summary(
    access_token: str,
    environment: str,
    account_id: str,
) -> dict[str, Any]:
    """Fetch account summary for a single OANDA account."""
    url = f"{base_url(environment)}/v3/accounts/{account_id}/summary"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=_auth_headers(access_token))
        response.raise_for_status()
        data = response.json()
    account = data.get("account") or {}
    return {
        "id": account.get("id"),
        "alias": account.get("alias"),
        "currency": account.get("currency"),
        "balance": account.get("balance"),
        "nav": account.get("NAV"),
        "unrealized_pl": account.get("unrealizedPL"),
        "realized_pl": account.get("pl"),
        "margin_available": account.get("marginAvailable"),
        "margin_used": account.get("marginUsed"),
        "open_trade_count": account.get("openTradeCount"),
        "open_position_count": account.get("openPositionCount"),
        "pending_order_count": account.get("pendingOrderCount"),
    }


async def test_connection(
    access_token: str,
    environment: str,
    account_id: str | None = None,
) -> tuple[bool, str, list[dict[str, Any]]]:
    """Verify OANDA credentials and optionally confirm a specific account.

    Returns (ok, message, accounts).
    """
    if not access_token.strip():
        return False, "OANDA access token is not configured", []
    if environment not in OANDA_ENVIRONMENTS:
        return False, f"Unknown OANDA environment '{environment}'", []

    try:
        accounts = await list_accounts(access_token, environment)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            return False, "Invalid OANDA access token", []
        if status == 403:
            return False, "Token is not authorized for this environment", []
        return False, f"OANDA returned HTTP {status}", []
    except httpx.HTTPError as exc:
        return False, f"OANDA request failed: {exc}", []

    if not accounts:
        return False, "No OANDA accounts are accessible with this token", []

    if account_id:
        if not any(acc["id"] == account_id for acc in accounts):
            return False, f"Account {account_id} is not accessible with this token", accounts
        return True, f"OANDA connection successful (account {account_id})", accounts

    return True, f"OANDA connection successful ({len(accounts)} account(s) found)", accounts


def forex_pair_to_instrument(pair: str) -> str:
    """Convert ``EUR/USD`` to OANDA instrument id ``EUR_USD``."""
    return pair.replace("/", "_").strip().upper()


OANDA_GRANULARITY_BY_TIMEFRAME: dict[str, str] = {
    "M1": "M1",
    "M2": "M2",
    "M4": "M4",
    "M5": "M5",
    "M10": "M10",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H2": "H2",
    "H3": "H3",
    "H4": "H4",
    "H6": "H6",
    "H8": "H8",
    "H12": "H12",
    "D1": "D",
    "W1": "W",
    "MN": "M",
}


def timeframe_to_granularity(timeframe: str) -> str | None:
    return OANDA_GRANULARITY_BY_TIMEFRAME.get(timeframe)


def normalize_oanda_candle(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a closed OANDA candle payload to a compact OHLCV dict."""
    if raw.get("complete") is not True:
        return None

    mid = raw.get("mid") or raw.get("bid") or raw.get("ask")
    if not isinstance(mid, dict):
        return None

    try:
        return {
            "time": raw["time"],
            "open": float(mid["o"]),
            "high": float(mid["h"]),
            "low": float(mid["l"]),
            "close": float(mid["c"]),
            "volume": int(raw.get("volume") or 0),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _parse_oanda_candles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for raw in payload.get("candles") or []:
        if not isinstance(raw, dict):
            continue
        normalized = normalize_oanda_candle(raw)
        if normalized is not None:
            candles.append(normalized)
    return candles


def _oanda_request_count(requested: int) -> int:
    """Request one extra bar so filtering incomplete candles still yields enough closed bars."""
    return max(1, min(int(requested) + 1, 5000))


def _trim_closed_candles(candles: list[dict[str, Any]], requested: int) -> list[dict[str, Any]]:
    if len(candles) <= requested:
        return candles
    return candles[-requested:]


async def fetch_candles(
    access_token: str,
    environment: str,
    instrument: str,
    granularity: str,
    count: int,
    *,
    price: str = "M",
) -> list[dict[str, Any]]:
    """Fetch mid OHLCV candles from OANDA."""
    if not access_token.strip():
        raise ValueError("OANDA access token is not configured")

    url = f"{base_url(environment)}/v3/instruments/{instrument}/candles"
    params = {
        "granularity": granularity,
        "count": _oanda_request_count(count),
        "price": price,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=_auth_headers(access_token), params=params)
        response.raise_for_status()
        payload = response.json()

    return _trim_closed_candles(_parse_oanda_candles(payload), count)


async def fetch_candles_to(
    access_token: str,
    environment: str,
    instrument: str,
    granularity: str,
    to_time: str,
    *,
    count: int = 5000,
    price: str = "M",
) -> list[dict[str, Any]]:
    """Fetch mid OHLCV candles from OANDA ending at *to_time* (exclusive)."""
    if not access_token.strip():
        raise ValueError("OANDA access token is not configured")

    url = f"{base_url(environment)}/v3/instruments/{instrument}/candles"
    params = {
        "granularity": granularity,
        "to": to_time,
        "count": _oanda_request_count(count),
        "price": price,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=_auth_headers(access_token), params=params)
        response.raise_for_status()
        payload = response.json()

    return _trim_closed_candles(_parse_oanda_candles(payload), count)


async def fetch_candles_from(
    access_token: str,
    environment: str,
    instrument: str,
    granularity: str,
    from_time: str,
    *,
    count: int = 5000,
    price: str = "M",
) -> list[dict[str, Any]]:
    """Fetch mid OHLCV candles from OANDA starting at *from_time* (inclusive)."""
    if not access_token.strip():
        raise ValueError("OANDA access token is not configured")

    url = f"{base_url(environment)}/v3/instruments/{instrument}/candles"
    params = {
        "granularity": granularity,
        "from": from_time,
        "count": _oanda_request_count(count),
        "price": price,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=_auth_headers(access_token), params=params)
        response.raise_for_status()
        payload = response.json()

    return _trim_closed_candles(_parse_oanda_candles(payload), count)
