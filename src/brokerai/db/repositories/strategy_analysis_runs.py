from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import StrategyAnalysisRunRow
from brokerai.trading.analysis_runs import (
    analysis_result_to_document,
    normalize_candle_time,
    serialize_analysis_run,
)
from brokerai.trading.types import AnalysisResult


def _normalize_trade_id(trade_id: str | None) -> str:
    return str(trade_id or "")


def _candle_time_for_db(value: datetime | str | None) -> datetime | None:
    """Normalize candle keys to UTC-aware datetimes for ``timestamptz`` columns.

    ``normalize_candle_time`` returns naive UTC for in-memory candle math. Postgres
    stores aware timestamps; comparing naive vs aware made ``_find_existing`` miss
    rows and then INSERT hit ``uq_strategy_analysis_runs_natural``.
    """
    when = normalize_candle_time(value)
    if when is None:
        return None
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _sync_row_columns(row: StrategyAnalysisRunRow, doc: dict[str, Any]) -> None:
    row.strategy_id = str(doc.get("strategy_id") or "")
    row.pair = str(doc.get("pair") or "")
    candle_dt = _candle_time_for_db(doc.get("candle_time"))
    if candle_dt is not None:
        row.candle_time = candle_dt
        doc["candle_time"] = candle_dt
    row.analysis_purpose = str(doc.get("analysis_purpose") or "entry")
    row.trade_id = _normalize_trade_id(doc.get("trade_id"))
    analyzed_at = doc.get("analyzed_at")
    if isinstance(analyzed_at, datetime):
        row.analyzed_at = (
            analyzed_at.astimezone(timezone.utc)
            if analyzed_at.tzinfo
            else analyzed_at.replace(tzinfo=timezone.utc)
        )
    row.doc = doc


class StrategyAnalysisRunsRepository:
    COLLECTION = "strategy_analysis_runs"

    @staticmethod
    def _dedupe_filter(
        *,
        strategy_id: str,
        pair: str,
        candle_time: datetime,
        analysis_purpose: str = "entry",
        trade_id: str | None = None,
    ) -> dict[str, Any]:
        purpose = analysis_purpose if analysis_purpose in {"entry", "exit"} else "entry"
        when = _candle_time_for_db(candle_time)
        if when is None:
            raise ValueError("candle_time is required for analysis-run dedupe")
        filt: dict[str, Any] = {
            "strategy_id": strategy_id,
            "pair": pair,
            "candle_time": when,
            "analysis_purpose": purpose,
        }
        if purpose == "exit" and trade_id:
            filt["trade_id"] = trade_id
        else:
            filt["trade_id"] = ""
        return filt

    @staticmethod
    def _merge_fields(existing: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
        update_fields: dict[str, Any] = {}
        purpose = str(doc.get("analysis_purpose") or "entry")
        if existing.get("run_type") != "manual":
            update_fields.update(
                {
                    "strategy_name": doc["strategy_name"],
                    "timeframe": doc["timeframe"],
                    "direction": doc["direction"],
                    "confidence": doc["confidence"],
                    "signal_type": doc["signal_type"],
                    "min_candles": doc["min_candles"],
                    "metadata": doc["metadata"],
                    "analyzed_at": doc["analyzed_at"],
                }
            )
        if purpose == "exit" and doc.get("execution") is not None:
            update_fields["execution"] = doc["execution"]
        if doc.get("run_type") == "manual" or existing.get("run_type") == "manual":
            update_fields["run_type"] = "manual"
        return update_fields

    async def _find_existing(self, filter_doc: dict[str, Any]) -> dict[str, Any] | None:
        async with session_scope() as session:
            stmt = select(StrategyAnalysisRunRow).where(
                StrategyAnalysisRunRow.strategy_id == filter_doc["strategy_id"],
                StrategyAnalysisRunRow.pair == filter_doc["pair"],
                StrategyAnalysisRunRow.candle_time == filter_doc["candle_time"],
                StrategyAnalysisRunRow.analysis_purpose == filter_doc["analysis_purpose"],
                StrategyAnalysisRunRow.trade_id == filter_doc.get("trade_id", ""),
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return dict(row.doc) if row else None

    async def find_by_strategy_pair_candle(
        self,
        *,
        strategy_id: str,
        pair: str,
        candle_time: datetime | str,
    ) -> dict[str, Any] | None:
        """Return an existing run for the same strategy, pair, and analyzed candle."""
        when = _candle_time_for_db(candle_time)
        if when is None:
            return None
        existing = await self._find_existing(
            self._dedupe_filter(strategy_id=strategy_id, pair=pair, candle_time=when)
        )
        if existing is None:
            return None
        return serialize_analysis_run(existing)

    async def _merge_existing(
        self,
        existing: dict[str, Any],
        doc: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = existing["id"]
        update_fields = self._merge_fields(existing, doc)
        if not update_fields:
            return existing

        merged = {**existing, **update_fields}
        async with session_scope() as session:
            row = await session.get(StrategyAnalysisRunRow, run_id)
            if row is None:
                return existing
            _sync_row_columns(row, merged)
        return merged

    async def _upsert_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        candle_dt = _candle_time_for_db(doc.get("candle_time"))
        strategy_id = str(doc.get("strategy_id") or "")
        pair = str(doc.get("pair") or "")
        purpose = str(doc.get("analysis_purpose") or "entry")
        trade_id = _normalize_trade_id(doc.get("trade_id"))
        doc["trade_id"] = trade_id if purpose == "exit" and trade_id else (trade_id or "")
        if candle_dt is not None:
            doc["candle_time"] = candle_dt

        if candle_dt is not None and strategy_id and pair:
            filter_doc = self._dedupe_filter(
                strategy_id=strategy_id,
                pair=pair,
                candle_time=candle_dt,
                analysis_purpose=purpose,
                trade_id=trade_id or None,
            )
            existing = await self._find_existing(filter_doc)
            if existing is not None:
                merged = await self._merge_existing(existing, doc)
                return serialize_analysis_run(merged)

            try:
                async with session_scope() as session:
                    bind = session.get_bind()
                    dialect = bind.dialect.name if bind is not None else "postgresql"
                    if dialect == "postgresql":
                        # Race-safe: concurrent pipeline retries must not crash Secretary.
                        values = {
                            "id": doc["id"],
                            "strategy_id": strategy_id,
                            "pair": pair,
                            "candle_time": candle_dt,
                            "analysis_purpose": purpose
                            if purpose in {"entry", "exit"}
                            else "entry",
                            "trade_id": doc["trade_id"],
                            "analyzed_at": (
                                doc["analyzed_at"]
                                if isinstance(doc.get("analyzed_at"), datetime)
                                else datetime.now(timezone.utc)
                            ),
                            "doc": doc,
                        }
                        if isinstance(values["analyzed_at"], datetime):
                            analyzed = values["analyzed_at"]
                            values["analyzed_at"] = (
                                analyzed.astimezone(timezone.utc)
                                if analyzed.tzinfo
                                else analyzed.replace(tzinfo=timezone.utc)
                            )
                        stmt = pg_insert(StrategyAnalysisRunRow).values(values)
                        stmt = stmt.on_conflict_do_nothing(
                            constraint="uq_strategy_analysis_runs_natural"
                        )
                        await session.execute(stmt)
                    else:
                        row = StrategyAnalysisRunRow(id=doc["id"], doc=doc)
                        _sync_row_columns(row, doc)
                        session.add(row)
            except IntegrityError:
                pass

            existing = await self._find_existing(filter_doc)
            if existing is not None:
                merged = await self._merge_existing(existing, doc)
                return serialize_analysis_run(merged)
            # Insert won the race (no prior row, conflict did nothing because we inserted).
            return serialize_analysis_run(doc)

        async with session_scope() as session:
            row = StrategyAnalysisRunRow(id=doc["id"], doc=doc)
            _sync_row_columns(row, doc)
            session.add(row)
        return serialize_analysis_run(doc)

    async def insert_from_result(
        self,
        result: AnalysisResult,
        *,
        candle_time: datetime | str | None,
    ) -> dict[str, Any]:
        doc = analysis_result_to_document(result, candle_time=candle_time)
        return await self._upsert_document(doc)

    async def insert_from_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Insert or merge a pre-built analysis run document (e.g. exit analysis)."""
        return await self._upsert_document(doc)

    async def list_recent(
        self,
        *,
        strategy_id: str | None = None,
        pair: str | None = None,
        analysis_purpose: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(StrategyAnalysisRunRow)
            if strategy_id:
                stmt = stmt.where(StrategyAnalysisRunRow.strategy_id == strategy_id)
            if pair:
                stmt = stmt.where(StrategyAnalysisRunRow.pair == pair)
            if analysis_purpose in {"entry", "exit"}:
                stmt = stmt.where(StrategyAnalysisRunRow.analysis_purpose == analysis_purpose)
            if before is not None:
                when = (
                    before.astimezone(timezone.utc)
                    if before.tzinfo
                    else before.replace(tzinfo=timezone.utc)
                )
                stmt = stmt.where(StrategyAnalysisRunRow.analyzed_at < when)
            stmt = stmt.order_by(StrategyAnalysisRunRow.analyzed_at.desc()).limit(
                max(1, min(limit, 200))
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [serialize_analysis_run(dict(row.doc)) for row in rows]

    async def get_by_id(self, run_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(StrategyAnalysisRunRow, run_id)
            if row is None:
                return None
            return serialize_analysis_run(dict(row.doc))

    async def update_execution(self, run_id: str, execution: dict[str, Any]) -> bool:
        async with session_scope() as session:
            row = await session.get(StrategyAnalysisRunRow, run_id)
            if row is None:
                return False
            doc = dict(row.doc)
            doc["execution"] = execution
            row.doc = doc
            return True

    async def delete_by_id(self, run_id: str) -> bool:
        """Remove a persisted analysis run by id."""
        async with session_scope() as session:
            result = await session.execute(
                delete(StrategyAnalysisRunRow).where(StrategyAnalysisRunRow.id == run_id)
            )
            return bool(result.rowcount)

    async def set_run_type(self, run_id: str, run_type: str) -> bool:
        """Update the persisted run type (e.g. ``live`` → ``manual``)."""
        async with session_scope() as session:
            row = await session.get(StrategyAnalysisRunRow, run_id)
            if row is None:
                return False
            doc = dict(row.doc)
            doc["run_type"] = run_type
            row.doc = doc
            return True
