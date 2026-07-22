"""Repositories for AI Strategy shadow intents/lots and trade outcomes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import ShadowIntentRow, ShadowLotRow, TradeOutcomeRecordRow


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ShadowIntentsRepository:
    async def upsert_intent(self, doc: dict[str, Any]) -> dict[str, Any]:
        strategy_id = str(doc["strategy_id"])
        pair = str(doc["pair"])
        direction = str(doc["direction"])
        entry_candle_open = str(doc.get("entry_candle_open") or "")
        async with session_scope() as session:
            existing = (
                await session.execute(
                    select(ShadowIntentRow).where(
                        ShadowIntentRow.strategy_id == strategy_id,
                        ShadowIntentRow.pair == pair,
                        ShadowIntentRow.entry_candle_open == entry_candle_open,
                        ShadowIntentRow.direction == direction,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                merged = {**doc, "id": existing.id}
                existing.doc = merged
                existing.phase = str(merged.get("phase") or existing.phase)
                existing.analysis_run_id = merged.get("analysis_run_id")
                existing.timeframe = str(merged.get("timeframe") or "")
                # Persist id last so callers never receive a regenerated UUID.
                return merged
            intent_id = str(doc.get("id") or uuid4().hex)
            merged = {**doc, "id": intent_id}
            session.add(
                ShadowIntentRow(
                    id=intent_id,
                    strategy_id=strategy_id,
                    pair=pair,
                    timeframe=str(merged.get("timeframe") or ""),
                    analysis_run_id=merged.get("analysis_run_id"),
                    phase=str(merged.get("phase") or "warming"),
                    direction=direction,
                    entry_candle_open=entry_candle_open,
                    created_at=_now(),
                    doc=merged,
                )
            )
            return merged

    async def list_for_strategy(self, strategy_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(ShadowIntentRow)
                    .where(ShadowIntentRow.strategy_id == strategy_id)
                    .order_by(ShadowIntentRow.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [{"id": row.id, **dict(row.doc)} for row in rows]


class ShadowLotsRepository:
    async def upsert_lot(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Upsert a shadow lot, idempotent on ``shadow_intent_id`` when present."""
        intent_id = doc.get("shadow_intent_id")
        async with session_scope() as session:
            row = None
            if intent_id:
                row = (
                    await session.execute(
                        select(ShadowLotRow)
                        .where(ShadowLotRow.shadow_intent_id == str(intent_id))
                        .limit(1)
                    )
                ).scalar_one_or_none()
            if row is None:
                lot_id = str(doc.get("id") or uuid4().hex)
                row = await session.get(ShadowLotRow, lot_id)
            if row is None:
                lot_id = str(doc.get("id") or uuid4().hex)
                merged = {**doc, "id": lot_id}
                session.add(
                    ShadowLotRow(
                        id=lot_id,
                        strategy_id=str(merged["strategy_id"]),
                        pair=str(merged["pair"]),
                        timeframe=str(merged.get("timeframe") or ""),
                        state=str(merged.get("state") or "open"),
                        direction=str(merged["direction"]),
                        shadow_intent_id=merged.get("shadow_intent_id"),
                        opened_at=_now(),
                        closed_at=None,
                        doc=merged,
                    )
                )
                return merged

            merged = {**doc, "id": row.id}
            if intent_id and not row.shadow_intent_id:
                row.shadow_intent_id = str(intent_id)
            row.doc = merged
            row.state = str(merged.get("state") or row.state)
            if row.state == "closed" and row.closed_at is None:
                row.closed_at = _now()
            return merged

    async def list_open(self, *, strategy_id: str | None = None, pair: str | None = None) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(ShadowLotRow).where(ShadowLotRow.state == "open")
            if strategy_id:
                stmt = stmt.where(ShadowLotRow.strategy_id == strategy_id)
            if pair:
                stmt = stmt.where(ShadowLotRow.pair == pair)
            rows = (await session.execute(stmt)).scalars().all()
            return [{"id": row.id, **dict(row.doc)} for row in rows]

    async def list_recent(self, *, limit: int = 100, strategy_id: str | None = None) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(ShadowLotRow).order_by(ShadowLotRow.opened_at.desc()).limit(limit)
            if strategy_id:
                stmt = stmt.where(ShadowLotRow.strategy_id == strategy_id)
            rows = (await session.execute(stmt)).scalars().all()
            return [{"id": row.id, **dict(row.doc), "state": row.state} for row in rows]

    async def close_lot(
        self,
        lot_id: str,
        *,
        exit_price: float,
        exit_reason: str,
        realized_pnl: float,
    ) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(ShadowLotRow, lot_id)
            if row is None:
                return None
            doc = dict(row.doc)
            doc.update(
                {
                    "state": "closed",
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "realized_pnl": realized_pnl,
                    "closed_at": _now().isoformat(),
                }
            )
            row.doc = doc
            row.state = "closed"
            row.closed_at = _now()
            return {"id": row.id, **doc}


class TradeOutcomeRecordsRepository:
    async def append(self, doc: dict[str, Any]) -> dict[str, Any]:
        outcome_id = str(doc.get("id") or uuid4().hex)
        entry_ts = doc.get("entry_ts")
        exit_ts = doc.get("exit_ts")
        if isinstance(entry_ts, str):
            entry_ts = datetime.fromisoformat(entry_ts.replace("Z", "+00:00"))
        if isinstance(exit_ts, str):
            exit_ts = datetime.fromisoformat(exit_ts.replace("Z", "+00:00"))
        if not isinstance(entry_ts, datetime):
            entry_ts = _now()
        if not isinstance(exit_ts, datetime):
            exit_ts = _now()
        async with session_scope() as session:
            session.add(
                TradeOutcomeRecordRow(
                    id=outcome_id,
                    strategy_id=str(doc["strategy_id"]),
                    mode=str(doc.get("mode") or "shadow"),
                    pair=str(doc["pair"]),
                    timeframe=str(doc.get("timeframe") or ""),
                    direction=str(doc["direction"]),
                    entry_ts=entry_ts,
                    exit_ts=exit_ts,
                    realized_pnl=float(doc.get("realized_pnl") or 0.0),
                    doc=doc,
                )
            )
        return {"id": outcome_id, **doc}

    async def list_for_strategy(self, strategy_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(TradeOutcomeRecordRow)
                    .where(TradeOutcomeRecordRow.strategy_id == strategy_id)
                    .order_by(TradeOutcomeRecordRow.exit_ts.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [{"id": row.id, **dict(row.doc)} for row in rows]

    async def count_since(
        self,
        strategy_id: str,
        *,
        since: datetime | None = None,
    ) -> int:
        """Count outcomes for a strategy with ``exit_ts`` strictly after ``since``.

        When ``since`` is None, counts all outcomes for the strategy.
        """
        async with session_scope() as session:
            stmt = (
                select(func.count())
                .select_from(TradeOutcomeRecordRow)
                .where(TradeOutcomeRecordRow.strategy_id == strategy_id)
            )
            if since is not None:
                stmt = stmt.where(TradeOutcomeRecordRow.exit_ts > since)
            return int((await session.execute(stmt)).scalar_one())

    async def list_since(
        self,
        strategy_id: str,
        *,
        since: datetime | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """List outcomes newest-first, optionally only those after ``since``."""
        limit = max(1, min(int(limit), 2000))
        async with session_scope() as session:
            stmt = select(TradeOutcomeRecordRow).where(
                TradeOutcomeRecordRow.strategy_id == strategy_id
            )
            if since is not None:
                stmt = stmt.where(TradeOutcomeRecordRow.exit_ts > since)
            stmt = stmt.order_by(TradeOutcomeRecordRow.exit_ts.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            out: list[dict[str, Any]] = []
            for row in rows:
                doc = dict(row.doc)
                out.append(
                    {
                        "id": row.id,
                        **doc,
                        "strategy_id": row.strategy_id,
                        "mode": row.mode,
                        "pair": row.pair,
                        "timeframe": row.timeframe,
                        "direction": row.direction,
                        "entry_ts": row.entry_ts.isoformat(),
                        "exit_ts": row.exit_ts.isoformat(),
                        "realized_pnl": float(row.realized_pnl or 0.0),
                    }
                )
            return out

    async def summarize_week(self, *, week_start: datetime, week_end: datetime) -> dict[str, Any]:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(TradeOutcomeRecordRow).where(
                        TradeOutcomeRecordRow.exit_ts >= week_start,
                        TradeOutcomeRecordRow.exit_ts <= week_end,
                    )
                )
            ).scalars().all()
        total = len(rows)
        wins = sum(1 for r in rows if float(r.realized_pnl or 0) > 0)
        losses = sum(1 for r in rows if float(r.realized_pnl or 0) < 0)
        pnl = sum(float(r.realized_pnl or 0) for r in rows)
        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "realized_pnl": pnl,
            "shadow": sum(1 for r in rows if r.mode == "shadow"),
            "live": sum(1 for r in rows if r.mode == "live"),
        }
