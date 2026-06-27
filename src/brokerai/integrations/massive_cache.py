from __future__ import annotations

import time
from typing import Any

from brokerai.integrations.massive import build_session_snapshot, fetch_market_status

_CACHE: dict[str, Any] = {"expires_at": 0.0, "api_key": "", "payload": None}
_TTL_SECONDS = 60.0


async def fetch_market_status_cached(api_key: str) -> tuple[bool, dict | str]:
    now = time.monotonic()
    key = api_key.strip()
    cached = _CACHE.get("payload")
    if (
        cached is not None
        and _CACHE.get("api_key") == key
        and now < float(_CACHE.get("expires_at") or 0)
    ):
        return True, cached

    ok, result = await fetch_market_status(key)
    if ok and isinstance(result, dict):
        _CACHE["api_key"] = key
        _CACHE["payload"] = result
        _CACHE["expires_at"] = now + _TTL_SECONDS
    return ok, result


def build_cached_session_snapshot(raw: dict) -> dict[str, Any]:
    return build_session_snapshot(raw)


def clear_market_status_cache() -> None:
    _CACHE["expires_at"] = 0.0
    _CACHE["payload"] = None
