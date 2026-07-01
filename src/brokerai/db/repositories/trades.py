from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.db.client import get_db
from brokerai.trading.analysis_runs import _format_dt
from brokerai.trading.trade_close_details import resolved_close_fields
from brokerai.trading.trade_reasons import resolve_trade_reason


def _execution_reason_from_metadata(metadata: dict[str, Any] | None) -> str | None:
    """Derive why an open trade was entered from persisted metadata."""
    if not metadata:
        return None
    explicit = metadata.get("execution_reason")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    analysis = metadata.get("analysis")
    if isinstance(analysis, dict):
        signal = analysis.get("signal")
        if isinstance(signal, str) and signal.strip() and signal != "none":
            return signal.strip()
    source = metadata.get("source")
    if source == "oanda_sync":
        return "oanda_import"
    if isinstance(source, str) and "place_random_oanda_trade" in source:
        return "random_trade"
    if isinstance(source, str) and source.strip():
        return source.strip()
    return None


def _resolved_execution_reason(doc: dict[str, Any]) -> str | None:
    stored = doc.get("execution_reason")
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    if doc.get("status") != "open":
        return None
    reason = _execution_reason_from_metadata(doc.get("metadata"))
    if reason:
        return reason
    if doc.get("strategy_id") == "test-script":
        return "random_trade"
    return None


def _reason_code_for_doc(doc: dict[str, Any]) -> str | None:
    if doc.get("status") == "closed":
        code = doc.get("close_reason")
        return str(code).strip() if code else None
    return _resolved_execution_reason(doc)


def serialize_trade(doc: dict[str, Any]) -> dict[str, Any]:
    """Normalize a trade document for JSON API responses."""
    close_fields = resolved_close_fields(doc)
    return {
        "id": doc.get("id"),
        "strategy_id": doc.get("strategy_id"),
        "strategy_name": doc.get("strategy_name"),
        "pair": doc.get("pair"),
        "asset_class": doc.get("asset_class", "forex"),
        "direction": doc.get("direction"),
        "entry_price": doc.get("entry_price"),
        "stop_loss": doc.get("stop_loss"),
        "take_profit": doc.get("take_profit"),
        "exit_mode": doc.get("exit_mode"),
        "risk_pct": doc.get("risk_pct"),
        "units": doc.get("units"),
        "confidence": doc.get("confidence"),
        "status": doc.get("status"),
        "broker_order_id": doc.get("broker_order_id"),
        "metadata": doc.get("metadata") or {},
        "trade_date": doc.get("trade_date"),
        "opened_at": _format_dt(doc.get("opened_at")),
        "closed_at": _format_dt(close_fields.get("closed_at") or doc.get("closed_at")),
        "close_reason": doc.get("close_reason"),
        "execution_reason": _resolved_execution_reason(doc),
        "close_metadata": doc.get("close_metadata") or {},
        "exit_price": close_fields.get("exit_price"),
        "realized_pl": close_fields.get("realized_pl"),
        "reason_display": resolve_trade_reason(_reason_code_for_doc(doc)),
        "created_at": _format_dt(doc.get("created_at")),
        "updated_at": _format_dt(doc.get("updated_at")),
    }


class TradesRepository:
    COLLECTION = "trades"

    async def create_open_trade(
        self,
        intent: dict[str, Any],
        *,
        broker_order_id: str | None = None,
        opened_at: datetime | None = None,
    ) -> dict[str, Any]:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        opened = opened_at.astimezone(timezone.utc) if opened_at is not None else now
        trade_id = uuid4().hex
        metadata = intent.get("metadata") or {}
        execution_reason = intent.get("execution_reason") or _execution_reason_from_metadata(metadata)
        document = {
            "id": trade_id,
            "strategy_id": intent.get("strategy_id"),
            "strategy_name": intent.get("strategy_name"),
            "pair": intent.get("pair"),
            "asset_class": intent.get("asset_class", "forex"),
            "direction": intent.get("direction"),
            "entry_price": intent.get("entry_price"),
            "stop_loss": intent.get("stop_loss"),
            "take_profit": intent.get("take_profit"),
            "exit_mode": intent.get("exit_mode"),
            "risk_pct": intent.get("risk_pct"),
            "units": intent.get("units"),
            "confidence": intent.get("confidence"),
            "status": "open",
            "broker_order_id": broker_order_id,
            "metadata": metadata,
            "execution_reason": execution_reason,
            "opened_at": opened,
            "trade_date": opened.date().isoformat(),
            "created_at": now,
            "updated_at": now,
        }
        await handle.db[self.COLLECTION].insert_one(document)
        return serialize_trade(document)

    async def get_open_by_broker_order_id(self, broker_order_id: str) -> dict[str, Any] | None:
        """Return an open trade linked to *broker_order_id*, if any."""
        if not broker_order_id.strip():
            return None
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            {"status": "open", "broker_order_id": broker_order_id},
            {"_id": 0},
        )
        if doc is None:
            return None
        return serialize_trade(doc)

    async def update_broker_order_id(self, trade_id: str, broker_order_id: str) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        await handle.db[self.COLLECTION].update_one(
            {"id": trade_id, "status": "open"},
            {"$set": {"broker_order_id": broker_order_id, "updated_at": now}},
        )

    async def close_trade(
        self,
        trade_id: str,
        *,
        reason: str,
        metadata: dict | None = None,
        exit_price: float | None = None,
        realized_pl: float | None = None,
        closed_at: datetime | None = None,
    ) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        closed = closed_at.astimezone(timezone.utc) if closed_at is not None else now
        updates: dict[str, Any] = {
            "status": "closed",
            "closed_at": closed,
            "close_reason": reason,
            "close_metadata": metadata or {},
            "updated_at": now,
        }
        if exit_price is not None:
            updates["exit_price"] = exit_price
        if realized_pl is not None:
            updates["realized_pl"] = realized_pl
        await handle.db[self.COLLECTION].update_one(
            {"id": trade_id},
            {"$set": updates},
        )

    async def backfill_close_details(
        self,
        trade_id: str,
        *,
        exit_price: float | None = None,
        realized_pl: float | None = None,
        closed_at: datetime | None = None,
    ) -> bool:
        """Patch missing close fields on an already-closed trade.

        Returns ``True`` when at least one field was written.
        """
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one({"id": trade_id, "status": "closed"}, {"_id": 0})
        if doc is None:
            return False

        updates: dict[str, Any] = {}
        if exit_price is not None and doc.get("exit_price") is None:
            updates["exit_price"] = exit_price
        if realized_pl is not None and doc.get("realized_pl") is None:
            updates["realized_pl"] = realized_pl
        if closed_at is not None and doc.get("closed_at") is None:
            updates["closed_at"] = closed_at.astimezone(timezone.utc)

        if not updates:
            return False

        updates["updated_at"] = datetime.now(timezone.utc)
        await handle.db[self.COLLECTION].update_one({"id": trade_id}, {"$set": updates})
        return True

    async def list_closed_trades_missing_close_details(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """Return closed trades that still lack exit price or realized P/L."""
        handle = await get_db()
        query: dict[str, Any] = {
            "status": "closed",
            "$or": [
                {"realized_pl": {"$exists": False}},
                {"realized_pl": None},
                {"exit_price": {"$exists": False}},
                {"exit_price": None},
            ],
        }
        cursor = (
            handle.db[self.COLLECTION]
            .find(query, {"_id": 0})
            .sort("closed_at", -1)
            .limit(max(1, min(limit, 200)))
        )
        return await cursor.to_list(length=limit)

    async def get_by_id(self, trade_id: str) -> dict[str, Any] | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one({"id": trade_id}, {"_id": 0})
        if doc is None:
            return None
        return serialize_trade(doc)

    async def list_trades(
        self,
        *,
        status: str = "open",
        strategy_id: str | None = None,
        pair: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """List trades filtered by status with optional pagination cursor.

        When *status* is ``all``, returns open trades first (``opened_at`` desc),
        then closed trades (``closed_at`` desc). Open trades are included in full up
        to 200 rows; *limit* caps the combined result size.

        For ``open`` or ``closed`` only, open trades sort by ``opened_at``
        descending and closed trades sort by ``closed_at`` descending. *before*
        excludes trades at or after that instant.
        """
        if status == "all":
            return await self._list_trades_combined(
                strategy_id=strategy_id,
                pair=pair,
                limit=limit,
                before=before,
            )

        handle = await get_db()
        query: dict[str, Any] = {"status": status}
        if strategy_id:
            query["strategy_id"] = strategy_id
        if pair:
            query["pair"] = pair

        sort_field = "closed_at" if status == "closed" else "opened_at"
        if before is not None:
            when = (
                before.astimezone(timezone.utc)
                if before.tzinfo
                else before.replace(tzinfo=timezone.utc)
            )
            query[sort_field] = {"$lt": when}

        cursor = (
            handle.db[self.COLLECTION]
            .find(query, {"_id": 0})
            .sort(sort_field, -1)
            .limit(max(1, min(limit, 200)))
        )
        rows = await cursor.to_list(length=limit)
        return [serialize_trade(row) for row in rows]

    async def _list_trades_combined(
        self,
        *,
        strategy_id: str | None = None,
        pair: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Open trades first (newest ``opened_at``), then closed (newest ``closed_at``)."""
        capped = max(1, min(limit, 200))
        open_trades = await self.list_trades(
            status="open",
            strategy_id=strategy_id,
            pair=pair,
            limit=min(capped, 200),
            before=before,
        )
        closed_limit = max(0, capped - len(open_trades))
        if closed_limit == 0:
            return open_trades
        closed_trades = await self.list_trades(
            status="closed",
            strategy_id=strategy_id,
            pair=pair,
            limit=closed_limit,
            before=before,
        )
        return open_trades + closed_trades

    async def list_open_trades(self) -> list[dict[str, Any]]:
        return await self.list_trades(status="open", limit=500)

    async def count_trades_today(self, strategy_id: str, pair: str, *, on_date: date | None = None) -> int:
        handle = await get_db()
        day = (on_date or datetime.now(timezone.utc).date()).isoformat()
        return await handle.db[self.COLLECTION].count_documents(
            {
                "strategy_id": strategy_id,
                "pair": pair,
                "trade_date": day,
            }
        )

    async def daily_trade_counts(self, *, on_date: date | None = None) -> dict[tuple[str, str], int]:
        handle = await get_db()
        day = (on_date or datetime.now(timezone.utc).date()).isoformat()
        pipeline = [
            {"$match": {"trade_date": day}},
            {"$group": {"_id": {"strategy_id": "$strategy_id", "pair": "$pair"}, "count": {"$sum": 1}}},
        ]
        rows = await handle.db[self.COLLECTION].aggregate(pipeline).to_list(length=1000)
        return {
            (row["_id"]["strategy_id"], row["_id"]["pair"]): int(row["count"])
            for row in rows
        }
