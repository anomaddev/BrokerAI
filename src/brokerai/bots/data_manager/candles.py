from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from brokerai.bots.data_manager.candle_requirements import (
    CandleRequirement,
    required_candle_bars,
    strategy_timeframe,
)
from brokerai.bots.researcher.concurrency import gather_limited
from brokerai.db.repositories.asset_settings import AssetSettingsRepository
from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.db.repositories.market_data import MarketDataRepository
from brokerai.integrations.oanda import (
    fetch_candles,
    fetch_candles_from,
    fetch_candles_to,
    forex_pair_to_instrument,
    timeframe_to_granularity,
)

logger = logging.getLogger(__name__)

OANDA_SOURCE = "oanda"
DEFAULT_FETCH_CONCURRENCY = 4
INCREMENTAL_BAR_COUNT = 2


@dataclass(frozen=True)
class CandleFetchResult:
    fetched: int
    errors: list[str]
    candles_upserted: int = 0


async def _resolve_forex_exchange() -> tuple[str | None, str | None]:
    settings = await AssetSettingsRepository().get("forex")
    exchange_id = settings.get("primary_exchange") or "oanda"
    return exchange_id, None


async def requirement_needs_bootstrap(
    requirement: CandleRequirement,
    repo: MarketDataRepository,
) -> bool:
    for pair in requirement.pairs:
        cached = await repo.count_candles(pair, requirement.timeframe, OANDA_SOURCE)
        if cached < requirement.bar_count:
            return True
    return False


async def load_candles_for_strategy(
    strategy: dict,
    pair: str,
    *,
    source: str = OANDA_SOURCE,
    repo: MarketDataRepository | None = None,
) -> list[dict]:
    """Return cached candles for a strategy, limited to its minimum required bars."""
    timeframe = strategy_timeframe(strategy)
    if not timeframe:
        return []

    market_repo = repo or MarketDataRepository()
    limit = required_candle_bars(strategy)
    return await market_repo.find_candles(pair, timeframe, source, limit=limit)


async def _fetch_pair_candles_incremental(
    pair: str,
    requirement: CandleRequirement,
    *,
    access_token: str,
    environment: str,
    repo: MarketDataRepository,
) -> tuple[list[dict], str | None]:
    granularity = timeframe_to_granularity(requirement.timeframe)
    if granularity is None:
        return [], f"{pair} {requirement.timeframe}: timeframe is not supported by OANDA"

    instrument = forex_pair_to_instrument(pair)
    latest_time = await repo.latest_candle_time(pair, requirement.timeframe, OANDA_SOURCE)
    if not latest_time:
        return [], None

    try:
        forward = await fetch_candles_from(
            access_token,
            environment,
            instrument,
            granularity,
            latest_time,
            count=INCREMENTAL_BAR_COUNT,
        )
    except httpx.HTTPStatusError as exc:
        return [], f"{pair} {requirement.timeframe}: OANDA returned HTTP {exc.response.status_code}"
    except httpx.HTTPError as exc:
        return [], f"{pair} {requirement.timeframe}: OANDA request failed ({exc})"
    except ValueError as exc:
        return [], f"{pair} {requirement.timeframe}: {exc}"

    candles = [candle for candle in forward if candle.get("time", "") > latest_time]
    return candles, None


async def _fetch_pair_candles_bootstrap(
    pair: str,
    requirement: CandleRequirement,
    *,
    access_token: str,
    environment: str,
    repo: MarketDataRepository,
) -> tuple[list[dict], str | None]:
    granularity = timeframe_to_granularity(requirement.timeframe)
    if granularity is None:
        return [], f"{pair} {requirement.timeframe}: timeframe is not supported by OANDA"

    instrument = forex_pair_to_instrument(pair)
    required = requirement.bar_count
    cached_count = await repo.count_candles(pair, requirement.timeframe, OANDA_SOURCE)
    candles: list[dict] = []

    try:
        if cached_count == 0:
            candles.extend(
                await fetch_candles(
                    access_token,
                    environment,
                    instrument,
                    granularity,
                    required,
                )
            )
        elif cached_count < required:
            earliest_time = await repo.earliest_candle_time(
                pair,
                requirement.timeframe,
                OANDA_SOURCE,
            )
            if earliest_time:
                missing = required - cached_count
                candles.extend(
                    await fetch_candles_to(
                        access_token,
                        environment,
                        instrument,
                        granularity,
                        earliest_time,
                        count=missing,
                    )
                )
    except httpx.HTTPStatusError as exc:
        return [], f"{pair} {requirement.timeframe}: OANDA returned HTTP {exc.response.status_code}"
    except httpx.HTTPError as exc:
        return [], f"{pair} {requirement.timeframe}: OANDA request failed ({exc})"
    except ValueError as exc:
        return [], f"{pair} {requirement.timeframe}: {exc}"

    if not candles:
        return [], None

    return candles, None


async def _fetch_pair_candles(
    pair: str,
    requirement: CandleRequirement,
    *,
    access_token: str,
    environment: str,
    repo: MarketDataRepository,
) -> tuple[list[dict], str | None]:
    if requirement.incremental:
        return await _fetch_pair_candles_incremental(
            pair,
            requirement,
            access_token=access_token,
            environment=environment,
            repo=repo,
        )
    return await _fetch_pair_candles_bootstrap(
        pair,
        requirement,
        access_token=access_token,
        environment=environment,
        repo=repo,
    )


async def _fetch_oanda_requirement(
    requirement: CandleRequirement,
    *,
    access_token: str,
    environment: str,
    repo: MarketDataRepository,
) -> tuple[int, str | None]:
    errors: list[str] = []
    upserted_total = 0
    pairs_cached = 0

    for pair in requirement.pairs:
        candles, error = await _fetch_pair_candles(
            pair,
            requirement,
            access_token=access_token,
            environment=environment,
            repo=repo,
        )
        if error:
            errors.append(error)
            continue
        if not candles:
            continue

        upserted = await repo.upsert_candles(
            pair,
            requirement.timeframe,
            OANDA_SOURCE,
            candles,
        )
        upserted_total += upserted
        pairs_cached += 1
        mode = "incremental" if requirement.incremental else "bootstrap"
        logger.info(
            "Cached %d candle(s) for %s %s (%s, %s)",
            upserted,
            pair,
            requirement.timeframe,
            OANDA_SOURCE,
            mode,
        )

    if pairs_cached == 0:
        if requirement.incremental:
            return 0, "; ".join(errors) if errors else None
        return 0, "; ".join(errors) if errors else f"{requirement.timeframe}: no candles fetched"

    return upserted_total, "; ".join(errors) if errors else None


async def fetch_and_cache_forex_candles(
    requirements: list[CandleRequirement],
    *,
    concurrency: int = DEFAULT_FETCH_CONCURRENCY,
) -> CandleFetchResult:
    if not requirements:
        return CandleFetchResult(fetched=0, errors=[])

    exchange_id, _ = await _resolve_forex_exchange()
    if exchange_id != OANDA_SOURCE:
        return CandleFetchResult(
            fetched=0,
            errors=[f"Candle fetch for exchange '{exchange_id}' is not implemented yet"],
        )

    oanda = await ExchangeConnectionsRepository().get_oanda()
    access_token = oanda.get("access_token") or ""
    environment = oanda.get("environment") or "practice"
    if not access_token.strip():
        return CandleFetchResult(
            fetched=0,
            errors=["OANDA is not configured in Settings → Data Connections"],
        )

    repo = MarketDataRepository()
    results = await gather_limited(
        [
            _fetch_oanda_requirement(
                requirement,
                access_token=access_token,
                environment=environment,
                repo=repo,
            )
            for requirement in requirements
        ],
        limit=concurrency,
    )

    errors: list[str] = []
    candles_upserted = 0
    fetched = 0
    for result in results:
        if isinstance(result, BaseException):
            errors.append(str(result))
            continue
        upserted, message = result
        if upserted > 0:
            fetched += 1
            candles_upserted += upserted
        if message:
            errors.append(message)

    return CandleFetchResult(fetched=fetched, errors=errors, candles_upserted=candles_upserted)
