from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import CostLedgerRow


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


def _billable_clause(billable_only: bool):
    if not billable_only:
        return None
    billable = CostLedgerRow.doc["metadata"]["billable"].as_string()
    return or_(billable.is_(None), billable != "false")


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
            # JSONB cannot store datetime objects — keep ISO string in doc.
            "occurred_at": when.isoformat(),
        }
        async with session_scope() as session:
            session.add(
                CostLedgerRow(
                    id=doc["id"],
                    category=category,
                    amount_usd=float(amount_usd or 0),
                    occurred_at=when,
                    doc=doc,
                )
            )
        return _serialize(doc)

    async def list_recent(
        self,
        *,
        category: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(CostLedgerRow)
            if category:
                stmt = stmt.where(CostLedgerRow.category == category)
            if before is not None:
                stmt = stmt.where(CostLedgerRow.occurred_at < _normalize_when(before))
            safe_limit = max(1, min(limit, 200))
            stmt = stmt.order_by(CostLedgerRow.occurred_at.desc()).limit(safe_limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_serialize(dict(row.doc)) for row in rows]

    async def summarize(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        category: str | None = None,
        billable_only: bool = True,
    ) -> dict[str, Any]:
        """Aggregate cost totals by category within an optional time window."""
        async with session_scope() as session:
            stmt = select(
                CostLedgerRow.category,
                func.coalesce(func.sum(CostLedgerRow.amount_usd), 0).label("amount_usd"),
                func.count().label("count"),
            )
            if category:
                stmt = stmt.where(CostLedgerRow.category == category)
            if since is not None:
                stmt = stmt.where(CostLedgerRow.occurred_at >= _normalize_when(since))
            if until is not None:
                stmt = stmt.where(CostLedgerRow.occurred_at <= _normalize_when(until))
            billable = _billable_clause(billable_only)
            if billable is not None:
                stmt = stmt.where(billable)
            stmt = stmt.group_by(CostLedgerRow.category).order_by(CostLedgerRow.category)
            rows = (await session.execute(stmt)).all()

        totals = [
            {
                "category": row.category,
                "amount_usd": round(float(row.amount_usd or 0), 6),
                "count": int(row.count or 0),
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
