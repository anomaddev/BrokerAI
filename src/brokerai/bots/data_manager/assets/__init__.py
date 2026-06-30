from __future__ import annotations

import logging

from brokerai.bots.base import WorkerResult
from brokerai.bots.data_manager.assets.base import stub_fetch_candles
from brokerai.bots.secretary.types import PipelineContext

logger = logging.getLogger(__name__)

_ASSET_CLASSES = ("stocks", "options", "futures", "metals", "crypto")


def get_asset_data_manager(asset_class: str):
    if asset_class == "forex":
        from brokerai.bots.data_manager.worker import DataManagerWorker

        return DataManagerWorker
    if asset_class in _ASSET_CLASSES:
        return None  # use stub_fetch_candles
    return None


async def run_asset_data_manager(context: PipelineContext) -> WorkerResult[PipelineContext]:
    if context.asset_class == "forex":
        from brokerai.bots.data_manager.worker import DataManagerWorker

        worker = DataManagerWorker()
        await worker.start()
        try:
            return await worker.run(context)
        finally:
            await worker.stop()
    return await stub_fetch_candles(context, context.asset_class)
