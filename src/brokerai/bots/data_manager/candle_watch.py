from __future__ import annotations

from brokerai.bots.data_manager.candle_requirements import CandleRequirement
from brokerai.db.repositories.candle_watch import CandleWatchRepository
from brokerai.trading.data.candle_cache import OANDA_SOURCE


async def collect_watch_requirements() -> list[CandleRequirement]:
    repo = CandleWatchRepository()
    watches = await repo.list_active_watches(source=OANDA_SOURCE)
    if not watches:
        return []

    merged: dict[tuple[str, str], int] = {}
    for watch in watches:
        symbol = str(watch.get("symbol") or "")
        timeframe = str(watch.get("timeframe") or "")
        if not symbol or not timeframe:
            continue
        bar_count = int(watch.get("bar_count") or 0)
        key = (symbol, timeframe)
        merged[key] = max(merged.get(key, 0), bar_count)

    return [
        CandleRequirement(
            timeframe=timeframe,
            pairs=(symbol,),
            bar_count=max(bar_count, 50),
        )
        for (symbol, timeframe), bar_count in sorted(merged.items())
    ]
