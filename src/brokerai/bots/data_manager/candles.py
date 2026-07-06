from __future__ import annotations

import logging
from dataclasses import dataclass

from brokerai.bots.data_manager.candle_requirements import CandleRequirement
from brokerai.bots.data_manager.service import DataManagerService
from brokerai.bots.researcher.concurrency import gather_limited
from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)

OANDA_SOURCE = "oanda"


@dataclass(frozen=True)
class CandleFetchResult:
    fetched: int
    errors: list[str]
    candles_upserted: int = 0


async def requirement_needs_warmup(
    requirement: CandleRequirement,
    service: DataManagerService,
) -> bool:
    """True when cache lacks the minimum bar count required for analysis."""
    for pair in requirement.pairs:
        count = await service.cache._market_repo.count_candles(
            pair,
            requirement.timeframe,
            OANDA_SOURCE,
        )
        if count < requirement.bar_count:
            return True
    return False


async def requirement_needs_bootstrap(
    requirement: CandleRequirement,
    service: DataManagerService,
) -> bool:
    """True when cache lacks bars or latest stored bar is behind the expected close."""
    if await requirement_needs_warmup(requirement, service):
        return True
    for pair in requirement.pairs:
        complete = await service.cache.is_cache_complete_up_to(
            pair,
            requirement.timeframe,
            source=OANDA_SOURCE,
        )
        if not complete:
            return True
    return False


async def fetch_and_cache_forex_candles(
    requirements: list[CandleRequirement],
    *,
    service: DataManagerService,
    concurrency: int | None = None,
) -> CandleFetchResult:
    if not requirements:
        return CandleFetchResult(fetched=0, errors=[])

    settings = get_settings()
    limit = concurrency or settings.candle_sync_concurrency
    errors: list[str] = []
    candles_upserted = 0
    fetched = 0

    async def _sync_requirement(requirement: CandleRequirement) -> tuple[int, str | None]:
        upserted_total = 0
        req_errors: list[str] = []
        for pair in requirement.pairs:
            if requirement.incremental:
                result = await service.sync(
                    pair,
                    requirement.timeframe,
                    incremental=True,
                )
            else:
                result = await service.sync(
                    pair,
                    requirement.timeframe,
                    bar_count=requirement.bar_count,
                )
            if result.error:
                req_errors.append(f"{pair} {requirement.timeframe}: {result.error}")
                continue
            if result.upserted:
                upserted_total += result.upserted
                mode = "incremental" if requirement.incremental else "bootstrap"
                logger.info(
                    "Cached %d candle(s) for %s %s (%s, %s)",
                    result.upserted,
                    pair,
                    requirement.timeframe,
                    OANDA_SOURCE,
                    mode,
                )
        if upserted_total == 0 and not requirement.incremental and req_errors:
            return 0, "; ".join(req_errors)
        return upserted_total, "; ".join(req_errors) if req_errors else None

    results = await gather_limited(
        [_sync_requirement(requirement) for requirement in requirements],
        limit=limit,
    )

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
