from __future__ import annotations

from typing import Any

from brokerai.db.client import get_db


class ResearchCacheRepository:
    COLLECTION = "research_cache"

    async def upsert(
        self,
        date: str,
        category: str,
        summary: str,
        sources: list[Any] | None = None,
    ) -> None:
        handle = await get_db()
        await handle.db[self.COLLECTION].update_one(
            {"date": date, "category": category},
            {
                "$set": {
                    "date": date,
                    "category": category,
                    "summary": summary,
                    "sources": sources or [],
                }
            },
            upsert=True,
        )

    async def find_by_date(self, date: str) -> list[dict[str, Any]]:
        handle = await get_db()
        cursor = handle.db[self.COLLECTION].find({"date": date}, {"_id": 0})
        return await cursor.to_list(length=100)
