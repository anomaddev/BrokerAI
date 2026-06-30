from __future__ import annotations

import logging
from typing import Protocol

from brokerai.bots.base import WorkerResult
from brokerai.bots.secretary.types import PipelineContext

logger = logging.getLogger(__name__)


class AssetDataManager(Protocol):
    asset_class: str

    async def fetch_candles(self, context: PipelineContext) -> WorkerResult[PipelineContext]: ...


async def stub_fetch_candles(
    context: PipelineContext,
    asset_class: str,
) -> WorkerResult[PipelineContext]:
    # TODO(loop): implement {asset_class} data manager
    logger.info(
        "TODO(loop): implement %s data manager for %s %s",
        asset_class,
        context.symbol,
        context.timeframe,
    )
    return WorkerResult(
        ok=True,
        data=context,
        metadata={"skipped": True, "reason": f"{asset_class} not implemented"},
    )
