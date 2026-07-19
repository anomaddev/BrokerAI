from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BotActivityRow


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    occurred_at = doc.get("occurred_at")
    if isinstance(occurred_at, datetime):
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        else:
            occurred_at = occurred_at.astimezone(timezone.utc)
        occurred_at = occurred_at.isoformat()
    return {
        "id": doc.get("id"),
        "action_type": doc.get("action_type"),
        "title": doc.get("title"),
        "detail": doc.get("detail"),
        "source": doc.get("source"),
        "metadata": doc.get("metadata") or {},
        "occurred_at": occurred_at,
    }


class BotActivityRepository:
    COLLECTION = "bot_activity"

    async def append(
        self,
        action_type: str,
        title: str,
        *,
        detail: str | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        when = occurred_at or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        else:
            when = when.astimezone(timezone.utc)

        doc = {
            "id": str(uuid4()),
            "action_type": action_type,
            "title": title.strip(),
            "detail": detail.strip() if detail else None,
            "source": source,
            "metadata": metadata or {},
            # JSONB cannot store datetime objects — keep ISO string in doc.
            "occurred_at": when.isoformat(),
        }
        async with session_scope() as session:
            session.add(
                BotActivityRow(id=doc["id"], occurred_at=when, doc=doc)
            )
        return _serialize(doc)

    async def list_recent(
        self,
        *,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(BotActivityRow)
            if before is not None:
                when = (
                    before.astimezone(timezone.utc)
                    if before.tzinfo
                    else before.replace(tzinfo=timezone.utc)
                )
                stmt = stmt.where(BotActivityRow.occurred_at < when)
            stmt = stmt.order_by(BotActivityRow.occurred_at.desc()).limit(
                max(1, min(limit, 200))
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_serialize(dict(row.doc)) for row in rows]
