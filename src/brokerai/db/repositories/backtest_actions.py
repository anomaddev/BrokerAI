"""Postgres repository for backtest action events (step-through review)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BacktestActionRow


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_instant(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def serialize_action(row: BacktestActionRow) -> dict[str, Any]:
    bar_time = None
    if row.bar_time is not None:
        bar_time = (
            row.bar_time.astimezone(timezone.utc).isoformat()
            if row.bar_time.tzinfo
            else row.bar_time.replace(tzinfo=timezone.utc).isoformat()
        )
    return {
        "id": row.id,
        "run_id": row.run_id,
        "sequence": row.sequence,
        "kind": row.kind,
        "message": row.message,
        "bar_time": bar_time,
        "meta": dict(row.meta) if isinstance(row.meta, dict) else row.meta,
        "created_at": row.created_at.astimezone(timezone.utc).isoformat()
        if row.created_at.tzinfo
        else row.created_at.replace(tzinfo=timezone.utc).isoformat(),
    }


def _action_values(run_id: str, action: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "sequence": int(action.get("sequence") or 0),
        "kind": str(action.get("kind") or "info"),
        "message": str(action.get("message") or ""),
        "bar_time": _parse_instant(action.get("bar_time")),
        "meta": dict(action["meta"]) if isinstance(action.get("meta"), dict) else None,
        "created_at": _parse_instant(action.get("created_at")) or _now_utc(),
    }


class BacktestActionsRepository:
    COLLECTION = "backtest_actions"

    async def insert_many(self, run_id: str, actions: list[dict[str, Any]]) -> int:
        if not actions:
            return 0
        async with session_scope() as session:
            bind = session.get_bind()
            dialect = bind.dialect.name if bind is not None else ""
            inserted = 0
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                for action in actions:
                    stmt = (
                        pg_insert(BacktestActionRow)
                        .values(**_action_values(run_id, action))
                        .on_conflict_do_nothing(constraint="uq_backtest_actions_run_sequence")
                    )
                    result = await session.execute(stmt)
                    inserted += int(result.rowcount or 0)
            else:
                for action in actions:
                    try:
                        async with session.begin_nested():
                            session.add(BacktestActionRow(**_action_values(run_id, action)))
                        inserted += 1
                    except IntegrityError:
                        pass
        return inserted

    async def list_for_run(
        self,
        run_id: str,
        *,
        after_sequence: int | None = None,
        kind: str | None = None,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(BacktestActionRow).where(BacktestActionRow.run_id == run_id)
            if after_sequence is not None:
                stmt = stmt.where(BacktestActionRow.sequence > after_sequence)
            if kind:
                stmt = stmt.where(BacktestActionRow.kind == kind)
            stmt = stmt.order_by(BacktestActionRow.sequence.asc()).limit(
                max(1, min(limit, 10000))
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [serialize_action(row) for row in rows]

    async def delete_for_run(self, run_id: str) -> int:
        async with session_scope() as session:
            result = await session.execute(
                delete(BacktestActionRow).where(BacktestActionRow.run_id == run_id)
            )
            return int(result.rowcount or 0)
