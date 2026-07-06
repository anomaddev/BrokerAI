from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from brokerai.bots.base import EphemeralBot, WorkerResult
from brokerai.bots.data_manager.candle_requirements import CandleRequirement
from brokerai.bots.data_manager.candles import OANDA_SOURCE, fetch_and_cache_forex_candles
from brokerai.bots.data_manager.service import DataManagerService, require_data_manager_service
from brokerai.bots.secretary.types import FetchStatus, PipelineContext
from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountSummaryRequest:
    asset_class: str


class DataManagerWorker(EphemeralBot[PipelineContext, PipelineContext]):
    """On-demand candle fetch/cache worker for Secretary pipelines."""

    name = "data_manager_worker"
    asset_class = "forex"

    async def run(self, request: PipelineContext) -> WorkerResult[PipelineContext]:
        service = require_data_manager_service()
        requirement = CandleRequirement(
            timeframe=request.timeframe,
            pairs=(request.symbol,),
            bar_count=request.bar_count,
        )
        incremental = request.incremental and not request.bootstrap
        to_fetch = [replace(requirement, incremental=incremental)]

        concurrency = get_settings().oanda_fetch_concurrency
        fetch_result = await fetch_and_cache_forex_candles(
            to_fetch,
            service=service,
            concurrency=concurrency,
        )

        latest = await service.latest_candle_time(
            request.symbol,
            request.timeframe,
            source=OANDA_SOURCE,
        )
        request.latest_candle_time = latest

        if fetch_result.errors:
            request.fetch_status = FetchStatus.PARTIAL if fetch_result.candles_upserted else FetchStatus.ERROR
            if not fetch_result.candles_upserted and not latest:
                return WorkerResult(
                    ok=False,
                    data=request,
                    error="; ".join(fetch_result.errors),
                    metadata={"errors": fetch_result.errors},
                )
        else:
            request.fetch_status = FetchStatus.OK if fetch_result.candles_upserted or latest else FetchStatus.SKIPPED

        return WorkerResult(
            ok=True,
            data=request,
            metadata={
                "candles_upserted": fetch_result.candles_upserted,
                "latest_candle_time": latest,
            },
        )


async def fetch_account_summary(request: AccountSummaryRequest) -> WorkerResult[dict]:
    """Fetch account summary for an asset class from MongoDB (synced every minute)."""
    if request.asset_class != "forex":
        return WorkerResult(
            ok=False,
            error=f"Account summary not implemented for {request.asset_class}",
        )

    from brokerai.trading.oanda_account_sync import get_cached_oanda_account_summary

    summary = await get_cached_oanda_account_summary(force_sync_if_missing=False)
    if summary is None:
        from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository

        oanda = await ExchangeConnectionsRepository().get_oanda()
        return WorkerResult(
            ok=True,
            data={
                "asset_class": request.asset_class,
                "account_id": oanda.get("account_id"),
                "connected": bool(oanda.get("access_token") and oanda.get("account_id")),
            },
        )

    snapshot = {
        "asset_class": request.asset_class,
        "account_id": summary.get("account_id") or summary.get("id"),
        "connected": True,
        **summary,
    }
    return WorkerResult(ok=True, data=snapshot)
