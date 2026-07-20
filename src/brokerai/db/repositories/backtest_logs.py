"""Postgres repository for backtest worker log lines."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BacktestLogRow


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def serialize_log(row: BacktestLogRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "level": row.level,
        "message": row.message,
        "meta": dict(row.meta) if isinstance(row.meta, dict) else row.meta,
        "created_at": row.created_at.astimezone(timezone.utc).isoformat()
        if row.created_at.tzinfo
        else row.created_at.replace(tzinfo=timezone.utc).isoformat(),
    }


class BacktestLogsRepository:
    COLLECTION = "backtest_logs"

    async def insert_many(
        self,
        run_id: str,
        entries: list[dict[str, Any]],
    ) -> int:
        if not entries:
            return 0
        async with session_scope() as session:
            for entry in entries:
                level = str(entry.get("level") or "INFO").upper()
                message = str(entry.get("message") or "")
                meta = entry.get("meta")
                created = entry.get("created_at")
                if isinstance(created, datetime):
                    created_at = (
                        created.astimezone(timezone.utc)
                        if created.tzinfo
                        else created.replace(tzinfo=timezone.utc)
                    )
                else:
                    created_at = _now_utc()
                session.add(
                    BacktestLogRow(
                        run_id=run_id,
                        level=level,
                        message=message,
                        meta=dict(meta) if isinstance(meta, dict) else None,
                        created_at=created_at,
                    )
                )
        return len(entries)

    async def list_for_run(
        self,
        run_id: str,
        *,
        after_id: int | None = None,
        limit: int = 500,
        level: str | None = None,
    ) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(BacktestLogRow).where(BacktestLogRow.run_id == run_id)
            if after_id is not None:
                stmt = stmt.where(BacktestLogRow.id > after_id)
            if level:
                stmt = stmt.where(BacktestLogRow.level == level.upper())
            stmt = stmt.order_by(BacktestLogRow.id.asc()).limit(max(1, min(limit, 2000)))
            rows = (await session.execute(stmt)).scalars().all()
            return [serialize_log(row) for row in rows]

    async def delete_for_run(self, run_id: str) -> int:
        async with session_scope() as session:
            result = await session.execute(
                delete(BacktestLogRow).where(BacktestLogRow.run_id == run_id)
            )
            return int(result.rowcount or 0)
