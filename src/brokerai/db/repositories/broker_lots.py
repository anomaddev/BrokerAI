from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.db.client import get_db
from brokerai.trading.analysis_runs import _format_dt
from brokerai.trading.broker.models import ChildOrder, PositionLot
from brokerai.trading.data.market_calendar import bar_open_string_for_instant
from brokerai.trading.trade_close_details import resolved_close_fields
from brokerai.trading.trade_reasons import resolve_trade_reason

logger = logging.getLogger(__name__)

DEFAULT_TRADE_CHART_TIMEFRAME = "M15"


def _resolve_lot_state(doc: dict[str, Any]) -> str:
    """Normalize open/closed/cancelled from ``state`` or ``status``."""
    for key in ("state", "status"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            normalized = value.strip().lower()
            if normalized in ("open", "closed", "cancelled"):
                return normalized
    return "open"


def _state_match_query(state: str) -> dict[str, Any]:
    """Mongo filter matching broker lot lifecycle state."""
    if state in ("closed", "cancelled", "open"):
        return {"state": state}
    return {}


def _quantities_from_doc(doc: dict[str, Any]) -> tuple[float, float]:
    """Resolve ``initial_qty`` / ``current_qty`` from lot or legacy ``units`` fields."""
    state = _resolve_lot_state(doc)
    legacy_units = doc.get("units")
    legacy_abs: float | None = None
    if legacy_units is not None:
        try:
            legacy_abs = abs(float(legacy_units))
        except (TypeError, ValueError):
            legacy_abs = None

    initial_raw = doc.get("initial_qty")
    current_raw = doc.get("current_qty")
    initial = float(initial_raw) if initial_raw is not None else None
    current = float(current_raw) if current_raw is not None else None

    if initial is None and legacy_abs is not None:
        initial = legacy_abs
    if current is None:
        if state == "open":
            current = initial if initial is not None else (legacy_abs or 0.0)
        else:
            current = 0.0
    if initial is None:
        initial = legacy_abs or current or 0.0

    return abs(float(initial)), abs(float(current))


def _effective_qty(doc: dict[str, Any]) -> float:
    initial_qty, current_qty = _quantities_from_doc(doc)
    if _resolve_lot_state(doc) == "open":
        return current_qty
    return initial_qty


_MIN_SORT_DT = datetime.min.replace(tzinfo=timezone.utc)


def _parse_sort_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _lot_last_modified(doc: dict[str, Any]) -> datetime:
    """Sort key aligned with the Trades UI “Last modified” column."""
    if _resolve_lot_state(doc) == "closed":
        for key in ("closed_at", "close_time", "updated_at", "opened_at", "open_time"):
            parsed = _parse_sort_datetime(doc.get(key))
            if parsed is not None:
                return parsed
    else:
        for key in ("opened_at", "open_time", "updated_at"):
            parsed = _parse_sort_datetime(doc.get(key))
            if parsed is not None:
                return parsed
    return _MIN_SORT_DT


def _sort_lots_by_last_modified(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=_lot_last_modified, reverse=True)


def _sort_lots_for_display(
    rows: list[dict[str, Any]],
    *,
    open_first: bool = False,
) -> list[dict[str, Any]]:
    """Sort by last modified descending; optionally pin open lots above closed."""
    if not open_first:
        return _sort_lots_by_last_modified(rows)

    def sort_key(doc: dict[str, Any]) -> tuple[int, float]:
        state = _resolve_lot_state(doc)
        if state == "open":
            group = 0
        elif state == "cancelled":
            group = 2
        else:
            group = 1
        return group, -_lot_last_modified(doc).timestamp()

    return sorted(rows, key=sort_key)


def _local_broker_id(doc: dict[str, Any]) -> str:
    return str(doc.get("broker_lot_id") or doc.get("broker_order_id") or "")


def _dedupe_open_lots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one open row per OANDA trade id (newest last-modified wins)."""
    by_broker_id: dict[str, dict[str, Any]] = {}
    orphans: list[dict[str, Any]] = []
    for row in rows:
        broker_id = _local_broker_id(row)
        if not broker_id:
            orphans.append(row)
            continue
        existing = by_broker_id.get(broker_id)
        if existing is None or _lot_last_modified(row) > _lot_last_modified(existing):
            by_broker_id[broker_id] = row
    return list(by_broker_id.values()) + orphans


def _execution_reason_from_metadata(metadata: dict[str, Any] | None) -> str | None:
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
    if doc.get("status") != "open" and doc.get("state") != "open":
        return None
    reason = _execution_reason_from_metadata(doc.get("metadata"))
    if reason:
        return reason
    if doc.get("strategy_id") == "test-script":
        return "random_trade"
    return None


def _reason_code_for_doc(doc: dict[str, Any]) -> str | None:
    state = _resolve_lot_state(doc)
    if state == "cancelled":
        code = doc.get("close_reason")
        return str(code).strip() if code else "order_cancelled"
    if state == "closed":
        code = doc.get("close_reason")
        return str(code).strip() if code else None
    return _resolved_execution_reason(doc)


def _child_order_to_doc(order: ChildOrder | None) -> dict[str, Any] | None:
    if order is None:
        return None
    return order.to_dict()


def _child_order_from_doc(raw: dict[str, Any] | None) -> ChildOrder | None:
    if not isinstance(raw, dict):
        return None
    return ChildOrder.from_dict(raw)


def fill_candle_anchors(
    lot_doc: dict[str, Any],
    *,
    strategy_timeframe: str | None = None,
) -> dict[str, Any]:
    """Return a copy of *lot_doc* with missing candle anchor fields derived from fill times.

    Never overwrites non-empty ``timeframe``, ``entry_candle_open``, or ``exit_candle_open``.
    """
    result = dict(lot_doc)
    timeframe = str(result.get("timeframe") or strategy_timeframe or DEFAULT_TRADE_CHART_TIMEFRAME)

    if not result.get("timeframe"):
        result["timeframe"] = timeframe

    open_instant = result.get("open_time") or result.get("opened_at")
    if not result.get("entry_candle_open") and open_instant:
        entry = bar_open_string_for_instant(open_instant, timeframe)
        if entry:
            result["entry_candle_open"] = entry

    state = _resolve_lot_state(result)
    close_instant = result.get("close_time") or result.get("closed_at")
    if state == "closed" and not result.get("exit_candle_open") and close_instant:
        exit_open = bar_open_string_for_instant(close_instant, timeframe)
        if exit_open:
            result["exit_candle_open"] = exit_open

    return result


def apply_candle_anchors_to_lot(
    lot: PositionLot,
    *,
    strategy_timeframe: str | None = None,
) -> PositionLot:
    """Fill missing candle anchor fields on *lot* in place."""
    doc = fill_candle_anchors(_lot_to_doc(lot), strategy_timeframe=strategy_timeframe)
    if not lot.timeframe:
        lot.timeframe = doc.get("timeframe")
    if not lot.entry_candle_open:
        lot.entry_candle_open = doc.get("entry_candle_open")
    if not lot.exit_candle_open:
        lot.exit_candle_open = doc.get("exit_candle_open")
    return lot


def _lot_to_doc(lot: PositionLot) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    open_time = lot.open_time or now
    trade_date = lot.trade_date or open_time.date().isoformat()
    return {
        "id": lot.id or uuid4().hex,
        "exchange_id": lot.exchange_id,
        "account_id": lot.account_id,
        "broker_lot_id": lot.broker_lot_id,
        "asset_class": lot.asset_class,
        "state": lot.state,
        "status": lot.state,
        "instrument": lot.instrument,
        "symbol": lot.symbol,
        "pair": lot.pair,
        "direction": lot.direction,
        "initial_qty": lot.initial_qty,
        "current_qty": lot.current_qty,
        "units": lot.units,
        "entry_price": lot.entry_price,
        "signal_entry_price": lot.signal_entry_price,
        "exit_price": lot.exit_price,
        "unrealized_pl": lot.unrealized_pl,
        "realized_pl": lot.realized_pl,
        "costs": lot.costs or {},
        "open_time": open_time,
        "close_time": lot.close_time,
        "opened_at": open_time,
        "closed_at": lot.close_time,
        "stop_loss": _child_order_to_doc(lot.stop_loss),
        "take_profit": _child_order_to_doc(lot.take_profit),
        "stop_loss_price": lot.stop_loss_price,
        "take_profit_price": lot.take_profit_price,
        "closing_event_ids": lot.closing_event_ids or [],
        "entry_batch_id": lot.entry_batch_id,
        "last_event_id": lot.last_event_id,
        "strategy_id": lot.strategy_id,
        "strategy_name": lot.strategy_name,
        "execution_reason": lot.execution_reason,
        "close_reason": lot.close_reason,
        "confidence": lot.confidence,
        "risk_pct": lot.risk_pct,
        "exit_mode": lot.exit_mode,
        "timeframe": lot.timeframe,
        "entry_candle_open": lot.entry_candle_open,
        "exit_candle_open": lot.exit_candle_open,
        "trade_date": trade_date,
        "synced_at": lot.synced_at or now,
        "raw_broker": lot.raw_broker,
        "broker_order_id": lot.broker_lot_id,
        "updated_at": now,
    }


def _lot_from_doc(doc: dict[str, Any]) -> PositionLot:
    pair = str(doc.get("pair") or "")
    symbol = str(doc.get("symbol") or doc.get("instrument") or pair.replace("/", "_"))
    initial_qty, current_qty = _quantities_from_doc(doc)
    return PositionLot(
        id=doc.get("id"),
        exchange_id=str(doc.get("exchange_id", "")),
        account_id=str(doc.get("account_id", "")),
        broker_lot_id=str(doc.get("broker_lot_id") or doc.get("broker_order_id") or ""),
        asset_class=str(doc.get("asset_class", "forex")),
        state=_resolve_lot_state(doc),
        instrument=symbol,
        symbol=symbol,
        direction=str(doc.get("direction", "long")),
        initial_qty=initial_qty,
        current_qty=current_qty,
        entry_price=float(doc.get("entry_price") or 0),
        signal_entry_price=doc.get("signal_entry_price"),
        exit_price=doc.get("exit_price"),
        unrealized_pl=doc.get("unrealized_pl"),
        realized_pl=doc.get("realized_pl"),
        costs=dict(doc.get("costs") or {}),
        open_time=doc.get("open_time") or doc.get("opened_at"),
        close_time=doc.get("close_time") or doc.get("closed_at"),
        stop_loss=_child_order_from_doc(doc.get("stop_loss")),
        take_profit=_child_order_from_doc(doc.get("take_profit")),
        stop_loss_price=doc.get("stop_loss_price"),
        take_profit_price=doc.get("take_profit_price"),
        closing_event_ids=list(doc.get("closing_event_ids") or []),
        entry_batch_id=doc.get("entry_batch_id"),
        last_event_id=doc.get("last_event_id"),
        strategy_id=doc.get("strategy_id"),
        strategy_name=doc.get("strategy_name"),
        execution_reason=doc.get("execution_reason"),
        close_reason=doc.get("close_reason"),
        confidence=doc.get("confidence"),
        risk_pct=doc.get("risk_pct"),
        exit_mode=doc.get("exit_mode"),
        timeframe=doc.get("timeframe"),
        entry_candle_open=doc.get("entry_candle_open"),
        exit_candle_open=doc.get("exit_candle_open"),
        trade_date=doc.get("trade_date"),
        synced_at=doc.get("synced_at"),
        raw_broker=doc.get("raw_broker"),
    )


def serialize_lot(doc: dict[str, Any]) -> dict[str, Any]:
    """Normalize a broker lot document for JSON API responses."""
    if doc.get("exit_price") is None or doc.get("realized_pl") is None:
        close_fields = resolved_close_fields(doc)
        if doc.get("exit_price") is None and close_fields.get("exit_price") is not None:
            doc = {**doc, "exit_price": close_fields["exit_price"]}
        if doc.get("realized_pl") is None and close_fields.get("realized_pl") is not None:
            doc = {**doc, "realized_pl": close_fields["realized_pl"]}
        if doc.get("closed_at") is None and close_fields.get("closed_at") is not None:
            doc = {**doc, "closed_at": close_fields["closed_at"]}
    lot = _lot_from_doc(doc)
    payload = lot.to_dict()
    reason_code = _reason_code_for_doc(doc)
    payload["reason_display"] = resolve_trade_reason(reason_code)
    payload["execution_reason"] = _resolved_execution_reason(doc)
    payload["metadata"] = doc.get("metadata") or {}
    payload["close_metadata"] = doc.get("close_metadata") or {}
    payload["created_at"] = _format_dt(doc.get("created_at"))
    payload["updated_at"] = _format_dt(doc.get("updated_at"))
    close_fields = resolved_close_fields(doc)
    if payload.get("exit_price") is None:
        payload["exit_price"] = close_fields.get("exit_price")
    if payload.get("realized_pl") is None:
        payload["realized_pl"] = close_fields.get("realized_pl")
    if payload.get("closed_at") is None:
        payload["closed_at"] = _format_dt(close_fields.get("closed_at") or doc.get("closed_at"))
    return payload


class BrokerLotsRepository:
    COLLECTION = "broker_lots"

    async def upsert_lot(self, lot: PositionLot, *, preserve_overlay: bool = True) -> dict[str, Any]:
        """Idempotent upsert by ``(exchange_id, account_id, broker_lot_id)``."""
        handle = await get_db()
        now = datetime.now(timezone.utc)

        if lot.broker_lot_id:
            await self._consolidate_duplicate_lots(
                lot.exchange_id,
                lot.broker_lot_id,
                preferred_account_id=lot.account_id or None,
            )

        existing = None
        if lot.broker_lot_id:
            existing = await handle.db[self.COLLECTION].find_one(
                {"exchange_id": lot.exchange_id, "broker_lot_id": lot.broker_lot_id},
                {"_id": 0},
            )

        account_id = lot.account_id
        if existing:
            account_id = str(existing.get("account_id") or lot.account_id or "")

        key = {
            "exchange_id": lot.exchange_id,
            "account_id": account_id,
            "broker_lot_id": lot.broker_lot_id,
        }
        if existing is None:
            existing = await handle.db[self.COLLECTION].find_one(key, {"_id": 0})

        doc = _lot_to_doc(lot)
        doc["account_id"] = account_id

        if existing:
            doc["id"] = existing.get("id")
            doc["created_at"] = existing.get("created_at", now)
            if preserve_overlay:
                for field in (
                    "strategy_id",
                    "strategy_name",
                    "execution_reason",
                    "confidence",
                    "risk_pct",
                    "exit_mode",
                    "stop_loss_price",
                    "take_profit_price",
                    "signal_entry_price",
                ):
                    if doc.get(field) is None and existing.get(field) is not None:
                        doc[field] = existing[field]
                # Candle anchors are strategy-derived and immutable once set. A sync
                # never sees the signal candle, so it derives these from the *fill*
                # time; letting that overwrite an existing anchor moves the trade
                # marker from the signal bar to the fill bar (which excludes the
                # bid/ask fill). Existing values always win when present.
                for field in ("timeframe", "entry_candle_open", "exit_candle_open"):
                    if existing.get(field) is not None:
                        doc[field] = existing[field]
        else:
            doc["created_at"] = now

        await handle.db[self.COLLECTION].update_one(key, {"$set": doc}, upsert=True)
        saved = await handle.db[self.COLLECTION].find_one({"id": doc["id"]}, {"_id": 0})
        if saved is None:
            saved = await handle.db[self.COLLECTION].find_one(key, {"_id": 0})
        assert saved is not None
        return serialize_lot(saved)

    async def _consolidate_duplicate_lots(
        self,
        exchange_id: str,
        broker_lot_id: str,
        *,
        preferred_account_id: str | None = None,
    ) -> None:
        """Remove duplicate rows for the same OANDA trade id (e.g. empty account_id)."""
        if not broker_lot_id:
            return
        handle = await get_db()
        cursor = handle.db[self.COLLECTION].find(
            {"exchange_id": exchange_id, "broker_lot_id": broker_lot_id},
            {"_id": 0},
        )
        docs = await cursor.to_list(length=20)
        if len(docs) <= 1:
            return

        def score(doc: dict[str, Any]) -> tuple[int, int, datetime]:
            account_id = str(doc.get("account_id") or "")
            preferred = int(bool(preferred_account_id and account_id == preferred_account_id))
            has_account = int(bool(account_id))
            updated = doc.get("updated_at")
            if not isinstance(updated, datetime):
                updated = _MIN_SORT_DT
            elif updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            return preferred, has_account, updated

        docs.sort(key=score, reverse=True)
        keeper = docs[0]
        for duplicate in docs[1:]:
            dup_id = duplicate.get("id")
            if dup_id and dup_id != keeper.get("id"):
                logger.info(
                    "Removing duplicate broker lot %s for trade %s (keeper=%s)",
                    dup_id,
                    broker_lot_id,
                    keeper.get("id"),
                )
                await handle.db[self.COLLECTION].delete_one({"id": dup_id})

    async def get_by_broker_lot_id(
        self,
        exchange_id: str,
        account_id: str,
        broker_lot_id: str,
    ) -> dict[str, Any] | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            {
                "exchange_id": exchange_id,
                "account_id": account_id,
                "broker_lot_id": broker_lot_id,
            },
            {"_id": 0},
        )
        return serialize_lot(doc) if doc else None

    async def get_by_id(self, lot_id: str) -> dict[str, Any] | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one({"id": lot_id}, {"_id": 0})
        if doc is None:
            return None
        return serialize_lot(doc)

    async def list_lots(
        self,
        *,
        exchange_id: str | None = None,
        state: str = "open",
        strategy_id: str | None = None,
        pair: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if state == "all":
            open_lots = await self._query_broker_lots(
                exchange_id=exchange_id,
                state="open",
                strategy_id=strategy_id,
                pair=pair,
                limit=min(limit, 200),
                before=before,
            )
            open_lots = _dedupe_open_lots(open_lots)
            closed_lots = await self._query_broker_lots(
                exchange_id=exchange_id,
                state="closed",
                strategy_id=strategy_id,
                pair=pair,
                limit=min(limit, 200),
                before=before,
            )
            return _sort_lots_for_display(open_lots + closed_lots, open_first=True)[:limit]

        rows = await self._query_broker_lots(
            exchange_id=exchange_id,
            state=state,
            strategy_id=strategy_id,
            pair=pair,
            limit=limit,
            before=before,
        )
        if state == "open":
            rows = _dedupe_open_lots(rows)
        return _sort_lots_by_last_modified(rows)[:limit]

    async def _query_broker_lots(
        self,
        *,
        exchange_id: str | None,
        state: str,
        strategy_id: str | None,
        pair: str | None,
        limit: int,
        before: datetime | None,
    ) -> list[dict[str, Any]]:
        handle = await get_db()
        query: dict[str, Any] = dict(_state_match_query(state))
        if exchange_id:
            query["exchange_id"] = exchange_id
        if strategy_id:
            query["strategy_id"] = strategy_id
        if pair:
            query["pair"] = pair.replace("_", "/")

        sort_field = "closed_at" if state == "closed" else "opened_at"
        if before is not None:
            when = before.astimezone(timezone.utc) if before.tzinfo else before.replace(tzinfo=timezone.utc)
            query[sort_field] = {"$lt": when}

        cursor = (
            handle.db[self.COLLECTION]
            .find(query, {"_id": 0})
            .sort(sort_field, -1)
            .limit(max(1, min(limit, 200)))
        )
        rows = await cursor.to_list(length=limit)
        return [serialize_lot(row) for row in rows]

    async def list_open_lots(
        self,
        *,
        exchange_id: str | None = None,
        strategy_id: str | None = None,
        dedupe: bool = True,
    ) -> list[dict[str, Any]]:
        rows = await self._query_broker_lots(
            exchange_id=exchange_id,
            state="open",
            strategy_id=strategy_id,
            pair=None,
            limit=500,
            before=None,
        )
        if dedupe:
            rows = _dedupe_open_lots(rows)
        return rows

    async def close_lot(
        self,
        lot_id: str,
        *,
        reason: str,
        exit_price: float | None = None,
        realized_pl: float | None = None,
        closed_at: datetime | None = None,
        exit_candle_open: str | None = None,
        close_metadata: dict[str, Any] | None = None,
    ) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        closed = closed_at.astimezone(timezone.utc) if closed_at else now
        updates: dict[str, Any] = {
            "state": "closed",
            "status": "closed",
            "close_reason": reason,
            "closed_at": closed,
            "close_time": closed,
            "current_qty": 0,
            "updated_at": now,
        }
        if exit_price is not None:
            updates["exit_price"] = exit_price
        if realized_pl is not None:
            updates["realized_pl"] = realized_pl
        if exit_candle_open:
            updates["exit_candle_open"] = exit_candle_open
        if close_metadata:
            updates["close_metadata"] = close_metadata
        await handle.db[self.COLLECTION].update_one({"id": lot_id}, {"$set": updates})

    async def cancel_lot(
        self,
        lot_id: str,
        *,
        reason: str,
        cancelled_at: datetime | None = None,
    ) -> None:
        """Mark a lot as cancelled (order rejected or cancelled before fill)."""
        handle = await get_db()
        now = datetime.now(timezone.utc)
        cancelled = cancelled_at.astimezone(timezone.utc) if cancelled_at else now
        await handle.db[self.COLLECTION].update_one(
            {"id": lot_id},
            {
                "$set": {
                    "state": "cancelled",
                    "status": "cancelled",
                    "close_reason": reason,
                    "closed_at": cancelled,
                    "close_time": cancelled,
                    "current_qty": 0,
                    "updated_at": now,
                }
            },
        )

    async def apply_strategy_overlay(
        self,
        exchange_id: str,
        account_id: str,
        broker_lot_id: str,
        overlay: dict[str, Any],
    ) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        await handle.db[self.COLLECTION].update_one(
            {
                "exchange_id": exchange_id,
                "account_id": account_id,
                "broker_lot_id": broker_lot_id,
            },
            {"$set": {**overlay, "updated_at": now}},
        )

    async def count_lots_today(
        self,
        strategy_id: str,
        pair: str,
        *,
        on_date: date | None = None,
    ) -> int:
        handle = await get_db()
        day = (on_date or datetime.now(timezone.utc).date()).isoformat()
        return await handle.db[self.COLLECTION].count_documents(
            {"strategy_id": strategy_id, "pair": pair.replace("_", "/"), "trade_date": day}
        )

    async def daily_lot_counts(self, *, on_date: date | None = None) -> dict[tuple[str, str], int]:
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

    async def list_closed_lots_missing_close_details(self, *, limit: int = 200) -> list[dict[str, Any]]:
        handle = await get_db()
        query: dict[str, Any] = {
            "$and": [
                _state_match_query("closed"),
                {
                    "$or": [
                        {"realized_pl": {"$exists": False}},
                        {"realized_pl": None},
                        {"exit_price": {"$exists": False}},
                        {"exit_price": None},
                    ],
                },
            ],
        }
        cursor = (
            handle.db[self.COLLECTION]
            .find(query, {"_id": 0})
            .sort("closed_at", -1)
            .limit(max(1, min(limit, 200)))
        )
        rows = await cursor.to_list(length=limit)
        return [serialize_lot(row) for row in rows]

    async def backfill_close_details(
        self,
        lot_id: str,
        *,
        exit_price: float | None = None,
        realized_pl: float | None = None,
        closed_at: datetime | None = None,
    ) -> bool:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one({"id": lot_id, "state": "closed"}, {"_id": 0})
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
        await handle.db[self.COLLECTION].update_one({"id": lot_id}, {"$set": updates})
        return True
