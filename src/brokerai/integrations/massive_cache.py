from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from brokerai.integrations.massive import build_session_snapshot, fetch_market_status

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {
    "expires_at": 0.0,
    "api_key": "",
    "payload": None,
    "last_error": None,
}
_TTL_SECONDS = 60.0
_LOCK = asyncio.Lock()


def _cache_valid(now: float, api_key: str) -> bool:
    cached = _CACHE.get("payload")
    return (
        cached is not None
        and _CACHE.get("api_key") == api_key
        and now < float(_CACHE.get("expires_at") or 0)
    )


async def fetch_market_status_cached(api_key: str) -> tuple[bool, dict | str]:
    """Return Massive market status, calling the API at most once per minute."""
    now = time.monotonic()
    key = api_key.strip()
    cached = _CACHE.get("payload")

    if _cache_valid(now, key):
        return True, cached

    async with _LOCK:
        now = time.monotonic()
        cached = _CACHE.get("payload")
        if _cache_valid(now, key):
            return True, cached

        ok, result = await fetch_market_status(key)
        if ok and isinstance(result, dict):
            _CACHE["api_key"] = key
            _CACHE["payload"] = result
            _CACHE["last_error"] = None
            _CACHE["expires_at"] = now + _TTL_SECONDS
            return True, result

        error = str(result)
        _CACHE["last_error"] = error
        _CACHE["expires_at"] = now + _TTL_SECONDS

        if cached is not None and _CACHE.get("api_key") == key:
            logger.warning(
                "Massive market status fetch failed (%s) — serving cached snapshot",
                error,
            )
            return True, cached

        return ok, result


def build_cached_session_snapshot(raw: dict) -> dict[str, Any]:
    return build_session_snapshot(raw)


def clear_market_status_cache() -> None:
    _CACHE["expires_at"] = 0.0
    _CACHE["payload"] = None
    _CACHE["last_error"] = None
