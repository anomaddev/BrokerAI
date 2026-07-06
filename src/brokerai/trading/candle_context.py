from __future__ import annotations

from brokerai.bots.data_manager.candles import OANDA_SOURCE
from brokerai.bots.data_manager.service import DataManagerService, require_data_manager_service
from brokerai.trading.types import WorkUnit


async def fetch_live_candles_for_unit(
    unit: WorkUnit,
    *,
    service: DataManagerService | None = None,
) -> list[dict]:
    """Fetch closed candles directly from OANDA for strategy analysis."""
    data_manager = service or require_data_manager_service()
    return await data_manager.fetch_live_candles_from_oanda(
        unit.pair,
        unit.timeframe,
        unit.bar_count,
    )


async def load_candles_for_unit(
    unit: WorkUnit,
    *,
    source: str = OANDA_SOURCE,
    service: DataManagerService | None = None,
    requester: str = "data_analyzer",
) -> list[dict]:
    """Load candles for a work unit via the Data Manager service."""
    if not unit.strategies:
        return []

    data_manager = service or require_data_manager_service()
    return await data_manager.request_candles(
        unit.pair,
        unit.timeframe,
        bar_count=unit.bar_count,
        source=source,
        requester=requester,
    )
