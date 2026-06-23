from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db


class MarketDataRepository:
    COLLECTION = "market_data"

    async def upsert(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        data: list[Any],
        *,
        expires_at: datetime | None = None,
    ) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        await handle.db[self.COLLECTION].update_one(
            {"symbol": symbol, "timeframe": timeframe, "source": source},
            {
                "$set": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "source": source,
                    "data": data,
                    "fetched_at": now,
                    "expires_at": expires_at,
                }
            },
            upsert=True,
        )

    async def find(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> dict[str, Any] | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            {"symbol": symbol, "timeframe": timeframe, "source": source},
            {"_id": 0},
        )
        return doc
