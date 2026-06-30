from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from brokerai.config.settings import get_settings


@dataclass
class _CacheEntry:
    candles: list[dict[str, Any]]
    expires_at: float


class PipelineCandleCache:
    """Short-lived in-process cache for hybrid Manager→Analyst handoff."""

    def __init__(self) -> None:
        self._entries: dict[str, _CacheEntry] = {}

    def _ttl(self) -> float:
        return float(get_settings().pipeline_candle_cache_ttl_seconds)

    def _key(self, symbol: str, timeframe: str, latest_candle_time: str) -> str:
        return f"{symbol}|{timeframe}|{latest_candle_time}"

    def store(
        self,
        symbol: str,
        timeframe: str,
        latest_candle_time: str,
        candles: list[dict[str, Any]],
    ) -> str:
        ref = self._key(symbol, timeframe, latest_candle_time)
        self._entries[ref] = _CacheEntry(
            candles=candles,
            expires_at=time.monotonic() + self._ttl(),
        )
        self._evict_expired()
        return ref

    def get(self, ref: str | None) -> list[dict[str, Any]] | None:
        if not ref:
            return None
        self._evict_expired()
        entry = self._entries.get(ref)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._entries[ref]
            return None
        return entry.candles

    def _evict_expired(self) -> None:
        now = time.monotonic()
        stale = [key for key, entry in self._entries.items() if now > entry.expires_at]
        for key in stale:
            del self._entries[key]


_GLOBAL_CACHE: PipelineCandleCache | None = None


def get_pipeline_candle_cache() -> PipelineCandleCache:
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is None:
        _GLOBAL_CACHE = PipelineCandleCache()
    return _GLOBAL_CACHE
