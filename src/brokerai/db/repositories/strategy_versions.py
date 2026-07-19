"""Per-strategy definition version history (explicit saves only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import StrategyVersionRow

MAX_VERSIONS_PER_STRATEGY = 50


def strategy_version_snapshot(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract the mutable definition fields stored on each version."""
    return {
        "name": str(doc.get("name") or ""),
        "description": str(doc.get("description") or ""),
        "params": dict(doc.get("params") or {}),
        "instrument_selection": dict(doc.get("instrument_selection") or {}),
        "enabled": bool(doc.get("enabled", False)),
        "preset_id": doc.get("preset_id"),
    }


def serialize_version_summary(row: StrategyVersionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "strategy_id": row.strategy_id,
        "version": row.version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "change_label": row.change_label or "",
    }


def serialize_version_detail(row: StrategyVersionRow) -> dict[str, Any]:
    payload = serialize_version_summary(row)
    payload["snapshot"] = dict(row.snapshot or {})
    return payload


async def _next_version_number(session: AsyncSession, strategy_id: str) -> int:
    stmt = select(func.coalesce(func.max(StrategyVersionRow.version), 0)).where(
        StrategyVersionRow.strategy_id == strategy_id
    )
    current = (await session.execute(stmt)).scalar_one()
    return int(current) + 1


async def _prune_old_versions(session: AsyncSession, strategy_id: str) -> None:
    """Keep only the newest ``MAX_VERSIONS_PER_STRATEGY`` rows for a strategy."""
    keep_stmt = (
        select(StrategyVersionRow.id)
        .where(StrategyVersionRow.strategy_id == strategy_id)
        .order_by(StrategyVersionRow.version.desc())
        .limit(MAX_VERSIONS_PER_STRATEGY)
    )
    keep_ids = list((await session.execute(keep_stmt)).scalars().all())
    if not keep_ids:
        return
    await session.execute(
        delete(StrategyVersionRow).where(
            StrategyVersionRow.strategy_id == strategy_id,
            StrategyVersionRow.id.not_in(keep_ids),
        )
    )


async def append_strategy_version(
    session: AsyncSession,
    *,
    strategy_id: str,
    snapshot: dict[str, Any],
    change_label: str,
    created_at: datetime | None = None,
) -> StrategyVersionRow:
    """Insert a version row and prune retention. Caller owns the transaction."""
    version_number = await _next_version_number(session, strategy_id)
    row = StrategyVersionRow(
        id=uuid4().hex,
        strategy_id=strategy_id,
        version=version_number,
        created_at=created_at or datetime.now(timezone.utc),
        change_label=(change_label or "").strip() or "Strategy updated",
        snapshot=snapshot,
    )
    session.add(row)
    await session.flush()
    await _prune_old_versions(session, strategy_id)
    return row


class StrategyVersionsRepository:
    """Read API for strategy definition versions."""

    async def list_for_strategy(
        self,
        strategy_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        async with session_scope() as session:
            count_stmt = (
                select(func.count())
                .select_from(StrategyVersionRow)
                .where(StrategyVersionRow.strategy_id == strategy_id)
            )
            total = int((await session.execute(count_stmt)).scalar_one())
            stmt = (
                select(StrategyVersionRow)
                .where(StrategyVersionRow.strategy_id == strategy_id)
                .order_by(StrategyVersionRow.version.desc())
                .offset(offset)
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [serialize_version_summary(row) for row in rows], total

    async def get_by_id(
        self,
        strategy_id: str,
        version_id: str,
    ) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(StrategyVersionRow, version_id)
            if not row or row.strategy_id != strategy_id:
                return None
            return serialize_version_detail(row)

    async def delete_for_strategy(self, session: AsyncSession, strategy_id: str) -> int:
        result = await session.execute(
            delete(StrategyVersionRow).where(StrategyVersionRow.strategy_id == strategy_id)
        )
        return int(result.rowcount or 0)
