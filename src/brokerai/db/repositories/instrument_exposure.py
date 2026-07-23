from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import InstrumentExposureRow
from brokerai.trading.analysis_runs import _format_dt
from brokerai.trading.broker.models import InstrumentExposure

logger = logging.getLogger(__name__)


def serialize_exposure_rollup(doc: dict[str, Any]) -> dict[str, Any]:
    """Normalize an exposure rollup document for JSON API responses."""
    symbol = str(doc.get("symbol") or "")
    return {
        **doc,
        "pair": str(doc.get("pair") or symbol.replace("_", "/")),
        "created_at": _format_dt(doc.get("created_at")),
        "updated_at": _format_dt(doc.get("updated_at")),
    }


def _rollup_from_lot_docs(lots: list[dict[str, Any]], *, exchange_id: str) -> list[InstrumentExposure]:
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for lot in lots:
        if str(lot.get("state") or "") != "open":
            continue
        symbol = str(lot.get("symbol") or lot.get("instrument") or "")
        if not symbol:
            continue
        direction = str(lot.get("direction") or "long").lower()
        account_id = str(lot.get("account_id") or "")
        buckets.setdefault((account_id, symbol, direction), []).append(lot)

    rollups: list[InstrumentExposure] = []
    for (account_id, symbol, direction), group in buckets.items():
        total_qty = sum(float(row.get("current_qty") or 0) for row in group)
        if total_qty <= 0:
            continue
        weighted_price = (
            sum(float(row.get("entry_price") or 0) * float(row.get("current_qty") or 0) for row in group)
            / total_qty
        )
        pl_values = [
            float(row.get("unrealized_pl"))
            for row in group
            if row.get("unrealized_pl") is not None
        ]
        rollups.append(
            InstrumentExposure(
                exchange_id=exchange_id,
                symbol=symbol,
                direction=direction,
                total_qty=total_qty,
                average_price=weighted_price,
                unrealized_pl=sum(pl_values) if pl_values else None,
                broker_lot_ids=[str(row.get("broker_lot_id") or "") for row in group if row.get("broker_lot_id")],
            )
        )
    return rollups


class InstrumentExposureRepository:
    COLLECTION = "instrument_exposure"

    async def upsert_rollup(self, exposure: InstrumentExposure, *, account_id: str) -> None:
        """Idempotently write one exposure rollup.

        Concurrent broker sync / secretary ticks can both observe a missing row and
        race on INSERT against ``uq_instrument_exposure``. Retry on IntegrityError;
        on Postgres also use ON CONFLICT so the losing writer updates instead of failing.
        """
        now = datetime.now(timezone.utc)
        base_doc = {
            **exposure.to_dict(),
            "account_id": account_id,
            "updated_at": now,
        }

        for attempt in range(3):
            try:
                async with session_scope() as session:
                    bind = session.get_bind()
                    dialect = bind.dialect.name if bind is not None else ""

                    row = (
                        await session.execute(
                            select(InstrumentExposureRow).where(
                                InstrumentExposureRow.exchange_id == exposure.exchange_id,
                                InstrumentExposureRow.account_id == account_id,
                                InstrumentExposureRow.symbol == exposure.symbol,
                                InstrumentExposureRow.direction == exposure.direction,
                            )
                        )
                    ).scalar_one_or_none()

                    if row is not None:
                        existing = dict(row.doc)
                        row.doc = {
                            **base_doc,
                            "created_at": existing.get("created_at", now),
                        }
                        return

                    insert_doc = {**base_doc, "created_at": now}
                    if dialect == "postgresql":
                        from sqlalchemy.dialects.postgresql import insert as pg_insert

                        stmt = pg_insert(InstrumentExposureRow).values(
                            exchange_id=exposure.exchange_id,
                            account_id=account_id,
                            symbol=exposure.symbol,
                            direction=exposure.direction,
                            doc=insert_doc,
                        )
                        stmt = stmt.on_conflict_do_update(
                            constraint="uq_instrument_exposure",
                            set_={"doc": stmt.excluded.doc},
                        )
                        await session.execute(stmt)
                        return

                    session.add(
                        InstrumentExposureRow(
                            exchange_id=exposure.exchange_id,
                            account_id=account_id,
                            symbol=exposure.symbol,
                            direction=exposure.direction,
                            doc=insert_doc,
                        )
                    )
                    return
            except IntegrityError:
                if attempt >= 2:
                    raise
                logger.debug(
                    "instrument_exposure upsert race on %s %s %s %s — retrying",
                    exposure.exchange_id,
                    account_id,
                    exposure.symbol,
                    exposure.direction,
                )

    async def recompute_for_account(
        self,
        *,
        exchange_id: str,
        account_id: str,
        open_lots: list[dict[str, Any]],
    ) -> int:
        """Rebuild all exposure rollups for an account from open lot documents.

        Upserts current keys first, then deletes orphans. Avoids delete-then-insert
        windows that race under concurrent syncs.
        """
        rollups = _rollup_from_lot_docs(open_lots, exchange_id=exchange_id)
        keep_keys = {(rollup.symbol, rollup.direction) for rollup in rollups}
        for rollup in rollups:
            await self.upsert_rollup(rollup, account_id=account_id)

        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(InstrumentExposureRow).where(
                        InstrumentExposureRow.exchange_id == exchange_id,
                        InstrumentExposureRow.account_id == account_id,
                    )
                )
            ).scalars().all()
            for row in rows:
                if (row.symbol, row.direction) not in keep_keys:
                    await session.delete(row)
        return len(rollups)

    async def list_for_account(
        self,
        *,
        exchange_id: str,
        account_id: str,
    ) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = (
                select(InstrumentExposureRow)
                .where(
                    InstrumentExposureRow.exchange_id == exchange_id,
                    InstrumentExposureRow.account_id == account_id,
                )
                .order_by(InstrumentExposureRow.symbol, InstrumentExposureRow.direction)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [serialize_exposure_rollup(dict(row.doc)) for row in rows]

    async def get_for_symbol(
        self,
        *,
        exchange_id: str,
        account_id: str,
        symbol: str,
        direction: str | None = None,
    ) -> InstrumentExposure | None:
        async with session_scope() as session:
            stmt = select(InstrumentExposureRow).where(
                InstrumentExposureRow.exchange_id == exchange_id,
                InstrumentExposureRow.account_id == account_id,
                InstrumentExposureRow.symbol == symbol,
            )
            if direction:
                stmt = stmt.where(InstrumentExposureRow.direction == direction.lower())
            row = (await session.execute(stmt)).scalar_one_or_none()
            if not row:
                return None
            doc = dict(row.doc)
            return InstrumentExposure(
                exchange_id=str(doc.get("exchange_id") or exchange_id),
                symbol=str(doc.get("symbol") or symbol),
                direction=str(doc.get("direction") or "long"),
                total_qty=float(doc.get("total_qty") or 0),
                average_price=doc.get("average_price"),
                unrealized_pl=doc.get("unrealized_pl"),
                broker_lot_ids=list(doc.get("broker_lot_ids") or []),
            )

    @staticmethod
    def rollups_to_local_by_key(
        rollups: list[dict[str, Any]],
    ) -> dict[tuple[str, str], float]:
        local: dict[tuple[str, str], float] = {}
        for doc in rollups:
            symbol = str(doc.get("symbol") or "")
            direction = str(doc.get("direction") or "long").lower()
            local[(symbol, direction)] = float(doc.get("total_qty") or 0)
        return local
