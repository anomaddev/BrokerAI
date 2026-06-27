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
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        handle = await get_db()
        doc: dict[str, Any] = {
            "date": date,
            "category": category,
            "summary": summary,
            "sources": sources or [],
        }
        if payload is not None:
            doc["payload"] = payload
        await handle.db[self.COLLECTION].update_one(
            {"date": date, "category": category},
            {"$set": doc},
            upsert=True,
        )

    async def find_by_date(self, date: str) -> list[dict[str, Any]]:
        handle = await get_db()
        cursor = handle.db[self.COLLECTION].find({"date": date}, {"_id": 0})
        return await cursor.to_list(length=100)

    async def find_latest_by_category(self, category: str) -> dict[str, Any] | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            {"category": category},
            {"_id": 0},
            sort=[("date", -1)],
        )
        return doc if isinstance(doc, dict) else None

    async def delete_one(self, date: str, category: str) -> None:
        handle = await get_db()
        await handle.db[self.COLLECTION].delete_one({"date": date, "category": category})
