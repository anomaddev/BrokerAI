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
