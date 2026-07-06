from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.db.client import get_db


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
        "category": doc.get("category"),
        "amount_usd": doc.get("amount_usd"),
        "description": doc.get("description"),
        "source": doc.get("source"),
        "metadata": doc.get("metadata") or {},
        "occurred_at": occurred_at,
    }


def _normalize_when(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


class CostLedgerRepository:
    COLLECTION = "cost_ledger"

    async def append(
        self,
        category: str,
        amount_usd: float | None,
        description: str,
        *,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        when = _normalize_when(occurred_at or datetime.now(timezone.utc))
        doc = {
            "id": str(uuid4()),
            "category": category,
            "amount_usd": amount_usd,
            "description": description.strip(),
            "source": source,
            "metadata": metadata or {},
            "occurred_at": when,
        }
        handle = await get_db()
        await handle.db[self.COLLECTION].insert_one(doc)
        return _serialize(doc)

    async def list_recent(
        self,
        *,
        category: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        handle = await get_db()
        query: dict[str, Any] = {}
        if category:
            query["category"] = category
        if before is not None:
            when = _normalize_when(before)
            query["occurred_at"] = {"$lt": when}

        safe_limit = max(1, min(limit, 200))
        cursor = (
            handle.db[self.COLLECTION]
            .find(query, {"_id": 0})
            .sort("occurred_at", -1)
            .limit(safe_limit)
        )
        rows = await cursor.to_list(length=safe_limit)
        return [_serialize(row) for row in rows]

    async def summarize(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        category: str | None = None,
        billable_only: bool = True,
    ) -> dict[str, Any]:
        """Aggregate cost totals by category within an optional time window."""
        handle = await get_db()
        match: dict[str, Any] = {}
        if category:
            match["category"] = category
        if billable_only:
            match["metadata.billable"] = {"$ne": False}

        occurred_at: dict[str, Any] = {}
        if since is not None:
            occurred_at["$gte"] = _normalize_when(since)
        if until is not None:
            occurred_at["$lte"] = _normalize_when(until)
        if occurred_at:
            match["occurred_at"] = occurred_at

        pipeline: list[dict[str, Any]] = []
        if match:
            pipeline.append({"$match": match})
        pipeline.extend(
            [
                {
                    "$group": {
                        "_id": "$category",
                        "amount_usd": {"$sum": {"$ifNull": ["$amount_usd", 0]}},
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"_id": 1}},
            ]
        )

        rows = await handle.db[self.COLLECTION].aggregate(pipeline).to_list(length=100)
        totals = [
            {
                "category": row["_id"],
                "amount_usd": round(float(row.get("amount_usd") or 0), 6),
                "count": int(row.get("count") or 0),
            }
            for row in rows
        ]
        grand_total = round(sum(item["amount_usd"] for item in totals), 6)
        return {
            "totals": totals,
            "grand_total_usd": grand_total,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        }
