from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db
from brokerai.trading.analysis_runs import _format_dt
from brokerai.trading.broker.models import InstrumentExposure, PositionLot

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
        handle = await get_db()
        now = datetime.now(timezone.utc)
        key = {
            "exchange_id": exposure.exchange_id,
            "account_id": account_id,
            "symbol": exposure.symbol,
            "direction": exposure.direction,
        }
        doc = {
            **exposure.to_dict(),
            "account_id": account_id,
            "updated_at": now,
        }
        existing = await handle.db[self.COLLECTION].find_one(key, {"_id": 0, "created_at": 1})
        if existing:
            doc["created_at"] = existing.get("created_at", now)
        else:
            doc["created_at"] = now
        await handle.db[self.COLLECTION].update_one(key, {"$set": doc}, upsert=True)

    async def recompute_for_account(
        self,
        *,
        exchange_id: str,
        account_id: str,
        open_lots: list[dict[str, Any]],
    ) -> int:
        """Rebuild all exposure rollups for an account from open lot documents."""
        handle = await get_db()
        await handle.db[self.COLLECTION].delete_many(
            {"exchange_id": exchange_id, "account_id": account_id},
        )
        rollups = _rollup_from_lot_docs(open_lots, exchange_id=exchange_id)
        for rollup in rollups:
            await self.upsert_rollup(rollup, account_id=account_id)
        return len(rollups)

    async def list_for_account(
        self,
        *,
        exchange_id: str,
        account_id: str,
    ) -> list[dict[str, Any]]:
        handle = await get_db()
        cursor = handle.db[self.COLLECTION].find(
            {"exchange_id": exchange_id, "account_id": account_id},
            {"_id": 0},
        ).sort([("symbol", 1), ("direction", 1)])
        rows = await cursor.to_list(length=500)
        return [serialize_exposure_rollup(row) for row in rows]

    async def get_for_symbol(
        self,
        *,
        exchange_id: str,
        account_id: str,
        symbol: str,
        direction: str | None = None,
    ) -> InstrumentExposure | None:
        handle = await get_db()
        query: dict[str, Any] = {
            "exchange_id": exchange_id,
            "account_id": account_id,
            "symbol": symbol,
        }
        if direction:
            query["direction"] = direction.lower()
        doc = await handle.db[self.COLLECTION].find_one(query, {"_id": 0})
        if not doc:
            return None
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
