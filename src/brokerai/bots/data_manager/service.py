from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from brokerai.trading.data.candle_cache import OANDA_SOURCE, CandleCache
from brokerai.trading.data.models import BackfillResult, CacheStatus, SyncResult, VerifyResult

logger = logging.getLogger(__name__)


class DataManagerUnavailableError(RuntimeError):
    """Raised when a consumer needs candles but Data Manager is not attached."""


@dataclass(frozen=True)
class _DemandKey:
    symbol: str
    timeframe: str
    source: str = OANDA_SOURCE


@dataclass
class _DemandEntry:
    bar_count: int = 0
    requesters: set[str] = field(default_factory=set)


class DataManagerService:
    """Public gateway for all candle data requests."""

    def __init__(self, *, cache: CandleCache | None = None) -> None:
        self._cache = cache or CandleCache()
        self._demand: dict[_DemandKey, _DemandEntry] = {}

    @classmethod
    def create_standalone(cls) -> DataManagerService:
        return cls()

    def _record_demand(
        self,
        symbol: str,
        timeframe: str,
        *,
        bar_count: int,
        source: str,
        requester: str,
    ) -> None:
        key = _DemandKey(symbol=symbol, timeframe=timeframe, source=source)
        entry = self._demand.setdefault(key, _DemandEntry())
        entry.bar_count = max(entry.bar_count, bar_count)
        entry.requesters.add(requester)

    def registered_demand(self) -> list[tuple[str, str, str, int]]:
        return [
            (key.symbol, key.timeframe, key.source, entry.bar_count)
            for key, entry in self._demand.items()
        ]

    async def request_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        bar_count: int,
        source: str = OANDA_SOURCE,
        since: str | None = None,
        until: str | None = None,
        sessions: list[str] | None = None,
        requester: str = "unknown",
    ) -> list[dict[str, Any]]:
        """Ensure cache satisfies the request, then return candles."""
        self._record_demand(symbol, timeframe, bar_count=bar_count, source=source, requester=requester)
        if since is not None and until is not None:
            await self._cache.backfill(symbol, timeframe, since, until, source=source)
            return await self._cache.read_candles(
                symbol,
                timeframe,
                source=source,
                bar_count=bar_count,
                since=since,
                until=until,
                sessions=sessions,
            )

        await self.ensure_coverage(
            symbol,
            timeframe,
            bar_count=bar_count,
            source=source,
            requester=requester,
        )
        return await self._cache.read_candles(
            symbol,
            timeframe,
            source=source,
            bar_count=bar_count,
            since=since,
            until=until,
            sessions=sessions,
        )

    async def ensure_coverage(
        self,
        symbol: str,
        timeframe: str,
        *,
        bar_count: int,
        source: str = OANDA_SOURCE,
        requester: str = "unknown",
    ) -> bool:
        self._record_demand(symbol, timeframe, bar_count=bar_count, source=source, requester=requester)
        count = await self._cache._market_repo.count_candles(symbol, timeframe, source)
        complete = await self._cache.is_cache_complete_up_to(symbol, timeframe, source=source)
        if count >= bar_count and complete:
            return True

        if count < bar_count:
            result = await self._cache.sync(
                symbol,
                timeframe,
                source=source,
                bar_count=bar_count,
            )
        else:
            result = await self._cache.sync(
                symbol,
                timeframe,
                source=source,
                incremental=True,
            )

        if result.error:
            logger.warning(
                "Data Manager — sync failed for %s %s (%s): %s",
                symbol,
                timeframe,
                requester,
                result.error,
            )
            return False

        return result.complete or count + result.upserted >= bar_count

    async def sync(
        self,
        symbol: str,
        timeframe: str,
        *,
        source: str = OANDA_SOURCE,
        bar_count: int | None = None,
        incremental: bool = False,
    ) -> SyncResult:
        result = await self._cache.sync(
            symbol,
            timeframe,
            source=source,
            bar_count=bar_count,
            incremental=incremental,
        )
        return result

    async def backfill(
        self,
        symbol: str,
        timeframe: str,
        start: str | datetime,
        end: str | datetime,
        *,
        source: str = OANDA_SOURCE,
    ) -> BackfillResult:
        return await self._cache.backfill(symbol, timeframe, start, end, source=source)

    async def fetch_candles_from_oanda(
        self,
        symbol: str,
        timeframe: str,
        since: str | datetime,
        until: str | datetime,
        *,
        price: str = "M",
    ) -> list[dict[str, Any]]:
        """Return lifecycle-window candles fetched directly from OANDA (no cache).

        ``price`` selects the OANDA candle component (``"M"`` mid, ``"B"`` bid, ``"A"``
        ask). Trade charts pass the execution side so broker fills sit inside the bars.
        """
        return await self._cache.fetch_range_from_oanda(
            symbol, timeframe, since, until, price=price
        )

    async def fetch_live_candles_from_oanda(
        self,
        symbol: str,
        timeframe: str,
        bar_count: int,
        *,
        until: datetime | None = None,
        price: str = "M",
    ) -> list[dict[str, Any]]:
        """Return ``bar_count`` closed candles from OANDA for live strategy analysis."""
        return await self._cache.fetch_count_from_oanda(
            symbol,
            timeframe,
            bar_count,
            until=until,
            price=price,
        )

    async def verify(
        self,
        symbol: str,
        timeframe: str,
        *,
        source: str = OANDA_SOURCE,
        days: int = 30,
    ) -> VerifyResult:
        return await self._cache.verify(symbol, timeframe, source=source, days=days)

    async def repair(
        self,
        symbol: str,
        timeframe: str,
        *,
        source: str = OANDA_SOURCE,
        days: int = 30,
    ) -> SyncResult:
        missing = await self._cache.get_missing_candles(
            symbol,
            timeframe,
            source=source,
            days=days,
        )
        return await self._cache.repair_missing(symbol, timeframe, missing, source=source)

    async def status(
        self,
        *,
        source: str = OANDA_SOURCE,
        symbols: list[tuple[str, str]] | None = None,
    ) -> list[CacheStatus]:
        return await self._cache.status(source=source, symbols=symbols)

    async def latest_candle_time(
        self,
        symbol: str,
        timeframe: str,
        *,
        source: str = OANDA_SOURCE,
    ) -> str | None:
        return await self._cache._market_repo.latest_candle_time(symbol, timeframe, source)

    @property
    def cache(self) -> CandleCache:
        return self._cache


_service: DataManagerService | None = None


def get_data_manager_service() -> DataManagerService | None:
    return _service


def set_data_manager_service(service: DataManagerService | None) -> None:
    global _service
    _service = service


def require_data_manager_service() -> DataManagerService:
    service = get_data_manager_service()
    if service is None:
        return DataManagerService.create_standalone()
    return service
