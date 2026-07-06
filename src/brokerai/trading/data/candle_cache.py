from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from brokerai.bots.data_manager.candle_schedule import timeframe_to_duration
from brokerai.config.settings import get_settings
from brokerai.db.repositories.candle_sync_state import CandleSyncStateRepository
from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.db.repositories.market_data import MarketDataRepository
from brokerai.integrations.oanda import (
    fetch_candles,
    fetch_candles_from,
    fetch_candles_range,
    fetch_candles_to,
    forex_pair_to_instrument,
    timeframe_to_granularity,
)
from brokerai.trading.data.market_calendar import (
    expected_latest_closed_bar,
    latest_closed_bar_time_string,
    missing_times_in_range,
    stored_time_matches_expected,
)
from brokerai.trading.data.models import BackfillResult, CacheStatus, SyncResult, VerifyResult
from brokerai.trading.data.session_enrichment import enrich_candles
from brokerai.trading.data.time_utils import format_oanda_time, parse_oanda_time

logger = logging.getLogger(__name__)

OANDA_SOURCE = "oanda"
INCREMENTAL_BAR_COUNT = 2


class CandleCache:
    """OANDA → MongoDB candle cache with bootstrap, incremental sync, and gap repair."""

    def __init__(
        self,
        *,
        market_repo: MarketDataRepository | None = None,
        sync_state_repo: CandleSyncStateRepository | None = None,
    ) -> None:
        self._market_repo = market_repo or MarketDataRepository()
        self._sync_state_repo = sync_state_repo or CandleSyncStateRepository()

    async def _oanda_credentials(self) -> tuple[str, str]:
        oanda = await ExchangeConnectionsRepository().get_oanda()
        token = str(oanda.get("access_token") or "").strip()
        environment = str(oanda.get("environment") or "practice")
        if not token:
            raise ValueError("OANDA access token is not configured")
        return token, environment

    async def is_cache_complete_up_to(
        self,
        symbol: str,
        timeframe: str,
        *,
        source: str = OANDA_SOURCE,
        as_of: datetime | None = None,
    ) -> bool:
        """True when the latest stored bar matches the expected latest closed bar."""
        latest_stored = await self._market_repo.latest_candle_time(symbol, timeframe, source)
        if not latest_stored:
            return False

        expected = expected_latest_closed_bar(timeframe, as_of=as_of)
        if expected is None:
            return True

        return stored_time_matches_expected(latest_stored, expected)

    async def read_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        source: str = OANDA_SOURCE,
        bar_count: int | None = None,
        since: str | None = None,
        until: str | None = None,
        sessions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if bar_count is not None and since is not None and until is not None:
            return await self._market_repo.find_candles(
                symbol,
                timeframe,
                source,
                since=since,
                until=until,
                limit=max(1, bar_count),
                ascending=True,
                sessions=sessions,
            )
        if bar_count is not None:
            return await self._market_repo.find_latest_candles(
                symbol,
                timeframe,
                source,
                limit=max(1, bar_count),
                since=since,
                until=until,
                sessions=sessions,
            )
        return await self._market_repo.find_candles(
            symbol,
            timeframe,
            source,
            since=since,
            until=until,
            sessions=sessions,
        )

    async def _fetch_bootstrap(
        self,
        symbol: str,
        timeframe: str,
        *,
        token: str,
        environment: str,
        instrument: str,
        granularity: str,
        bar_count: int,
    ) -> list[dict[str, Any]]:
        stored_count = await self._market_repo.count_candles(symbol, timeframe, OANDA_SOURCE)
        if stored_count == 0:
            return await fetch_candles(
                token,
                environment,
                instrument,
                granularity,
                bar_count,
            )

        earliest = await self._market_repo.earliest_candle_time(symbol, timeframe, OANDA_SOURCE)
        if not earliest:
            return await fetch_candles(
                token,
                environment,
                instrument,
                granularity,
                bar_count,
            )

        needed = max(0, bar_count - stored_count)
        chunk = min(
            max(needed + 10, bar_count),
            get_settings().candle_sync_chunk_size,
        )
        backward = await fetch_candles_to(
            token,
            environment,
            instrument,
            granularity,
            earliest,
            count=chunk,
        )
        return [candle for candle in backward if str(candle.get("time", "")) < earliest]

    async def _fetch_incremental(
        self,
        symbol: str,
        timeframe: str,
        *,
        token: str,
        environment: str,
        instrument: str,
        granularity: str,
    ) -> list[dict[str, Any]]:
        latest = await self._market_repo.latest_candle_time(symbol, timeframe, OANDA_SOURCE)
        if not latest:
            return []

        raw = await fetch_candles_from(
            token,
            environment,
            instrument,
            granularity,
            latest,
            count=INCREMENTAL_BAR_COUNT,
        )
        return [candle for candle in raw if str(candle.get("time", "")) > latest]

    async def sync(
        self,
        symbol: str,
        timeframe: str,
        *,
        source: str = OANDA_SOURCE,
        bar_count: int | None = None,
        incremental: bool = False,
    ) -> SyncResult:
        if source != OANDA_SOURCE:
            return SyncResult(
                symbol=symbol,
                timeframe=timeframe,
                error=f"Unsupported candle source: {source}",
            )

        granularity = timeframe_to_granularity(timeframe)
        if granularity is None:
            return SyncResult(
                symbol=symbol,
                timeframe=timeframe,
                error=f"Unsupported timeframe for OANDA: {timeframe}",
            )

        try:
            token, environment = await self._oanda_credentials()
        except ValueError as exc:
            return SyncResult(symbol=symbol, timeframe=timeframe, error=str(exc))

        instrument = forex_pair_to_instrument(symbol)
        stored_count = await self._market_repo.count_candles(symbol, timeframe, source)

        try:
            if incremental:
                fetched = await self._fetch_incremental(
                    symbol,
                    timeframe,
                    token=token,
                    environment=environment,
                    instrument=instrument,
                    granularity=granularity,
                )
            elif bar_count is not None and stored_count < bar_count:
                fetched = await self._fetch_bootstrap(
                    symbol,
                    timeframe,
                    token=token,
                    environment=environment,
                    instrument=instrument,
                    granularity=granularity,
                    bar_count=bar_count,
                )
            else:
                fetched = await self._fetch_incremental(
                    symbol,
                    timeframe,
                    token=token,
                    environment=environment,
                    instrument=instrument,
                    granularity=granularity,
                )
        except Exception as exc:
            logger.exception("Candle sync failed for %s %s", symbol, timeframe)
            await self._sync_state_repo.upsert_state(
                symbol,
                timeframe,
                source,
                last_error=str(exc),
            )
            return SyncResult(symbol=symbol, timeframe=timeframe, error=str(exc))

        enriched = enrich_candles(fetched)
        upserted = await self._market_repo.upsert_candles(symbol, timeframe, source, enriched)
        complete = await self.is_cache_complete_up_to(symbol, timeframe, source=source)
        expected_str = latest_closed_bar_time_string(timeframe)
        latest_after = await self._market_repo.latest_candle_time(symbol, timeframe, source)

        await self._sync_state_repo.upsert_state(
            symbol,
            timeframe,
            source,
            high_water_time=latest_after,
            expected_latest=expected_str,
            last_error=None,
        )

        return SyncResult(
            symbol=symbol,
            timeframe=timeframe,
            upserted=upserted,
            complete=complete,
        )

    async def get_missing_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        source: str = OANDA_SOURCE,
        days: int = 30,
    ) -> list[str]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, days))
        stored = await self._market_repo.find_candle_times(
            symbol,
            timeframe,
            source,
            since=format_oanda_time(start),
            until=format_oanda_time(end),
        )
        return missing_times_in_range(stored, start, end, timeframe)

    async def verify(
        self,
        symbol: str,
        timeframe: str,
        *,
        source: str = OANDA_SOURCE,
        days: int = 30,
    ) -> VerifyResult:
        missing = await self.get_missing_candles(
            symbol,
            timeframe,
            source=source,
            days=days,
        )
        complete = len(missing) == 0 and await self.is_cache_complete_up_to(
            symbol,
            timeframe,
            source=source,
        )
        return VerifyResult(
            symbol=symbol,
            timeframe=timeframe,
            missing_count=len(missing),
            missing_times=missing,
            complete=complete,
        )

    async def repair_missing(
        self,
        symbol: str,
        timeframe: str,
        missing_times: list[str],
        *,
        source: str = OANDA_SOURCE,
    ) -> SyncResult:
        if source != OANDA_SOURCE:
            return SyncResult(
                symbol=symbol,
                timeframe=timeframe,
                error=f"Unsupported candle source: {source}",
            )
        if not missing_times:
            complete = await self.is_cache_complete_up_to(symbol, timeframe, source=source)
            return SyncResult(symbol=symbol, timeframe=timeframe, complete=complete)

        granularity = timeframe_to_granularity(timeframe)
        if granularity is None:
            return SyncResult(
                symbol=symbol,
                timeframe=timeframe,
                error=f"Unsupported timeframe: {timeframe}",
            )

        try:
            token, environment = await self._oanda_credentials()
        except ValueError as exc:
            return SyncResult(symbol=symbol, timeframe=timeframe, error=str(exc))

        instrument = forex_pair_to_instrument(symbol)
        sorted_times = sorted(missing_times)
        start = parse_oanda_time(sorted_times[0])
        end = parse_oanda_time(sorted_times[-1])
        chunk_size = get_settings().candle_sync_chunk_size

        try:
            fetched = await fetch_candles_range(
                token,
                environment,
                instrument,
                granularity,
                format_oanda_time(start),
                format_oanda_time(end),
                max_chunk=chunk_size,
            )
        except Exception as exc:
            return SyncResult(symbol=symbol, timeframe=timeframe, error=str(exc))

        missing_set = set(missing_times)
        to_store = [c for c in fetched if str(c.get("time", "")) in missing_set]
        enriched = enrich_candles(to_store)
        upserted = await self._market_repo.upsert_candles(symbol, timeframe, source, enriched)
        complete = await self.is_cache_complete_up_to(symbol, timeframe, source=source)
        return SyncResult(
            symbol=symbol,
            timeframe=timeframe,
            upserted=upserted,
            complete=complete,
        )

    def _normalize_range_bounds(
        self,
        start: str | datetime,
        end: str | datetime,
    ) -> tuple[str, str]:
        """Return OANDA-formatted ``(start_str, end_str)`` for a candle range."""
        if isinstance(start, datetime):
            start_dt = start.astimezone(timezone.utc) if start.tzinfo else start.replace(tzinfo=timezone.utc)
            start_str = format_oanda_time(start_dt)
        else:
            start_str = str(start)
            if "T" not in start_str:
                start_dt = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
                start_str = format_oanda_time(start_dt)

        if isinstance(end, datetime):
            end_dt = end.astimezone(timezone.utc) if end.tzinfo else end.replace(tzinfo=timezone.utc)
            end_str = format_oanda_time(end_dt)
        else:
            end_str = str(end)
            if "T" not in end_str:
                end_dt = datetime.fromisoformat(end_str).replace(tzinfo=timezone.utc)
                end_str = format_oanda_time(end_dt)

        return start_str, end_str

    async def fetch_count_from_oanda(
        self,
        symbol: str,
        timeframe: str,
        bar_count: int,
        *,
        until: datetime | None = None,
        price: str = "M",
    ) -> list[dict[str, Any]]:
        """Fetch ``bar_count`` closed candles directly from OANDA (never reads MongoDB).

        When ``until`` is set it must be the analyzed candle **open** time; OANDA's
        exclusive ``to`` bound is derived as ``until + one bar`` so the anchor bar
        is included. When ``until`` is omitted, returns the latest ``bar_count`` bars.
        """
        granularity = timeframe_to_granularity(timeframe)
        if granularity is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        count = max(1, int(bar_count))
        token, environment = await self._oanda_credentials()
        instrument = forex_pair_to_instrument(symbol)

        if until is None:
            raw = await fetch_candles(
                token,
                environment,
                instrument,
                granularity,
                count,
                price=price,
            )
        else:
            anchor = until.astimezone(timezone.utc) if until.tzinfo else until.replace(tzinfo=timezone.utc)
            to_exclusive = format_oanda_time(anchor + timeframe_to_duration(timeframe))
            raw = await fetch_candles_to(
                token,
                environment,
                instrument,
                granularity,
                to_exclusive,
                count=count,
                price=price,
            )

        return enrich_candles(raw)

    async def fetch_range_from_oanda(
        self,
        symbol: str,
        timeframe: str,
        start: str | datetime,
        end: str | datetime,
        *,
        price: str = "M",
    ) -> list[dict[str, Any]]:
        """Fetch closed candles from OANDA for ``[start, end]`` without touching MongoDB.

        Used for trade detail charts where the lifecycle window must come directly from
        the broker rather than the explore cache.

        Args:
            price: OANDA candle price component: ``"M"`` (mid, default), ``"B"`` (bid)
                or ``"A"`` (ask). Trade charts pass the *execution* side (ask for longs,
                bid for shorts) so the recorded fill sits inside the candle range instead
                of poking above the high / below the low by the half-spread. Mid candles
                are never the price a market order actually fills at.

        Raises:
            ValueError: OANDA credentials missing or timeframe unsupported.
        """
        granularity = timeframe_to_granularity(timeframe)
        if granularity is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        start_str, end_str = self._normalize_range_bounds(start, end)
        if start_str > end_str:
            return []

        token, environment = await self._oanda_credentials()
        instrument = forex_pair_to_instrument(symbol)
        chunk_size = get_settings().candle_sync_chunk_size
        collected: list[dict[str, Any]] = []
        cursor = start_str

        while cursor <= end_str:
            batch = await fetch_candles_range(
                token,
                environment,
                instrument,
                granularity,
                cursor,
                end_str,
                max_chunk=chunk_size,
                price=price,
            )
            if not batch:
                break
            collected.extend(enrich_candles(batch))
            last_time = str(batch[-1]["time"])
            if last_time >= end_str or len(batch) < chunk_size:
                break
            last_dt = parse_oanda_time(last_time)
            cursor = format_oanda_time(last_dt + timeframe_to_duration(timeframe))

        return collected

    async def backfill(
        self,
        symbol: str,
        timeframe: str,
        start: str | datetime,
        end: str | datetime,
        *,
        source: str = OANDA_SOURCE,
    ) -> BackfillResult:
        if source != OANDA_SOURCE:
            return BackfillResult(
                symbol=symbol,
                timeframe=timeframe,
                error=f"Unsupported candle source: {source}",
            )

        granularity = timeframe_to_granularity(timeframe)
        if granularity is None:
            return BackfillResult(
                symbol=symbol,
                timeframe=timeframe,
                error=f"Unsupported timeframe: {timeframe}",
            )

        start_str, end_str = self._normalize_range_bounds(start, end)

        try:
            token, environment = await self._oanda_credentials()
        except ValueError as exc:
            return BackfillResult(symbol=symbol, timeframe=timeframe, error=str(exc))

        instrument = forex_pair_to_instrument(symbol)
        chunk_size = get_settings().candle_sync_chunk_size
        chunks = 0
        total_upserted = 0
        cursor = start_str

        try:
            while cursor <= end_str:
                batch = await fetch_candles_range(
                    token,
                    environment,
                    instrument,
                    granularity,
                    cursor,
                    end_str,
                    max_chunk=chunk_size,
                )
                chunks += 1
                if not batch:
                    break
                enriched = enrich_candles(batch)
                total_upserted += await self._market_repo.upsert_candles(
                    symbol,
                    timeframe,
                    source,
                    enriched,
                )
                last_time = str(batch[-1]["time"])
                if last_time >= end_str or len(batch) < chunk_size:
                    break
                cursor = last_time
        except Exception as exc:
            return BackfillResult(
                symbol=symbol,
                timeframe=timeframe,
                upserted=total_upserted,
                chunks=chunks,
                error=str(exc),
            )

        return BackfillResult(
            symbol=symbol,
            timeframe=timeframe,
            upserted=total_upserted,
            chunks=chunks,
        )

    async def status(
        self,
        *,
        source: str = OANDA_SOURCE,
        symbols: list[tuple[str, str]] | None = None,
    ) -> list[CacheStatus]:
        rows: list[CacheStatus] = []

        if symbols:
            pairs = symbols
        else:
            states = await self._sync_state_repo.list_states(source=source)
            pairs = [(str(s["symbol"]), str(s["timeframe"])) for s in states]

        for symbol, timeframe in pairs:
            count = await self._market_repo.count_candles(symbol, timeframe, source)
            latest = await self._market_repo.latest_candle_time(symbol, timeframe, source)
            complete = await self.is_cache_complete_up_to(symbol, timeframe, source=source)
            rows.append(
                CacheStatus(
                    symbol=symbol,
                    timeframe=timeframe,
                    count=count,
                    latest_time=latest,
                    complete=complete,
                )
            )
        return rows
