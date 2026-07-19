from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import ResearchCacheRow


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
        doc: dict[str, Any] = {
            "date": date,
            "category": category,
            "summary": summary,
            "sources": sources or [],
        }
        if payload is not None:
            doc["payload"] = payload

        async with session_scope() as session:
            stmt = select(ResearchCacheRow).where(
                ResearchCacheRow.date == date,
                ResearchCacheRow.category == category,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                session.add(ResearchCacheRow(date=date, category=category, doc=doc))
            else:
                row.doc = doc

    async def find_by_date(self, date: str) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(ResearchCacheRow).where(ResearchCacheRow.date == date)
            rows = (await session.execute(stmt)).scalars().all()
            return [dict(row.doc) for row in rows]

    async def find_latest_by_category(self, category: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            stmt = (
                select(ResearchCacheRow)
                .where(ResearchCacheRow.category == category)
                .order_by(ResearchCacheRow.date.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return dict(row.doc) if row else None

    async def delete_one(self, date: str, category: str) -> None:
        async with session_scope() as session:
            await session.execute(
                delete(ResearchCacheRow).where(
                    ResearchCacheRow.date == date,
                    ResearchCacheRow.category == category,
                )
            )
