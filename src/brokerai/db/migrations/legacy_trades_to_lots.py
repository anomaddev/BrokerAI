"""Convert legacy ``trades`` collection documents into ``broker_lots`` format."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.repositories.broker_lots import _quantities_from_doc, _resolve_lot_state

_OVERLAY_FIELDS = frozenset(
    {
        "strategy_id",
        "strategy_name",
        "execution_reason",
        "confidence",
        "risk_pct",
        "exit_mode",
        "stop_loss_price",
        "take_profit_price",
        "metadata",
        "close_metadata",
        "close_reason",
    }
)


def _legacy_priority(doc: dict[str, Any]) -> tuple[int, int, datetime]:
    """Prefer strategy-attributed rows over ``oanda-import`` duplicates."""
    strategy_id = str(doc.get("strategy_id") or "")
    is_import = int(strategy_id == "oanda-import")
    has_strategy = int(bool(strategy_id and strategy_id != "oanda-import"))
    updated = doc.get("updated_at") or doc.get("closed_at") or doc.get("opened_at")
    if not isinstance(updated, datetime):
        updated = datetime.min.replace(tzinfo=timezone.utc)
    elif updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return has_strategy, -is_import, updated


def pick_best_legacy_per_broker(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return one legacy trade per ``broker_order_id`` (best overlay candidate)."""
    grouped: dict[str, dict[str, Any]] = {}
    for trade in trades:
        broker_id = str(trade.get("broker_order_id") or trade.get("broker_lot_id") or "").strip()
        if not broker_id:
            continue
        existing = grouped.get(broker_id)
        if existing is None or _legacy_priority(trade) > _legacy_priority(existing):
            grouped[broker_id] = trade
    return grouped


def overlay_from_legacy(trade: dict[str, Any]) -> dict[str, Any]:
    """Strategy overlay fields to merge onto an existing broker lot."""
    stop_loss = trade.get("stop_loss")
    take_profit = trade.get("take_profit")
    overlay: dict[str, Any] = {
        "strategy_id": trade.get("strategy_id"),
        "strategy_name": trade.get("strategy_name"),
        "execution_reason": trade.get("execution_reason")
        or (trade.get("metadata") or {}).get("execution_reason"),
        "confidence": trade.get("confidence"),
        "risk_pct": trade.get("risk_pct"),
        "exit_mode": trade.get("exit_mode"),
        "stop_loss_price": stop_loss if isinstance(stop_loss, (int, float)) else trade.get("stop_loss_price"),
        "take_profit_price": take_profit
        if isinstance(take_profit, (int, float))
        else trade.get("take_profit_price"),
        "metadata": trade.get("metadata") or {},
        "close_metadata": trade.get("close_metadata") or {},
        "close_reason": trade.get("close_reason"),
    }
    return {k: v for k, v in overlay.items() if v is not None}


def legacy_trade_to_lot_doc(trade: dict[str, Any]) -> dict[str, Any]:
    """Build a full ``broker_lots`` document from a legacy trade row."""
    state = _resolve_lot_state(trade)
    broker_id = str(trade.get("broker_order_id") or trade.get("broker_lot_id") or "")
    pair = str(trade.get("pair") or "")
    symbol = str(trade.get("symbol") or trade.get("instrument") or pair.replace("/", "_"))
    initial_qty, current_qty = _quantities_from_doc(trade)
    opened_at = trade.get("opened_at") or trade.get("open_time") or trade.get("created_at")
    closed_at = trade.get("closed_at") or trade.get("close_time")
    trade_date = trade.get("trade_date")
    if not trade_date and isinstance(opened_at, datetime):
        trade_date = opened_at.date().isoformat()

    direction = str(trade.get("direction") or "long")
    units = abs(current_qty if state == "open" else initial_qty)
    if direction == "short":
        units = -units

    now = datetime.now(timezone.utc)
    stop_loss = trade.get("stop_loss")
    take_profit = trade.get("take_profit")

    doc: dict[str, Any] = {
        "id": trade.get("id"),
        "exchange_id": trade.get("exchange_id") or "oanda",
        "account_id": str(trade.get("account_id") or ""),
        "broker_lot_id": broker_id,
        "broker_order_id": broker_id,
        "asset_class": trade.get("asset_class") or "forex",
        "state": state,
        "status": state,
        "instrument": symbol,
        "symbol": symbol,
        "pair": pair or symbol.replace("_", "/"),
        "direction": direction,
        "initial_qty": initial_qty,
        "current_qty": current_qty if state == "open" else 0.0,
        "units": units,
        "entry_price": float(trade.get("entry_price") or 0),
        "exit_price": trade.get("exit_price"),
        "unrealized_pl": trade.get("unrealized_pl"),
        "realized_pl": trade.get("realized_pl"),
        "costs": dict(trade.get("costs") or {}),
        "open_time": opened_at,
        "opened_at": opened_at,
        "close_time": closed_at if state == "closed" else None,
        "closed_at": closed_at if state == "closed" else None,
        "stop_loss": None,
        "take_profit": None,
        "stop_loss_price": stop_loss if isinstance(stop_loss, (int, float)) else trade.get("stop_loss_price"),
        "take_profit_price": take_profit
        if isinstance(take_profit, (int, float))
        else trade.get("take_profit_price"),
        "closing_event_ids": list(trade.get("closing_event_ids") or []),
        "entry_batch_id": trade.get("entry_batch_id"),
        "last_event_id": trade.get("last_event_id"),
        "strategy_id": trade.get("strategy_id"),
        "strategy_name": trade.get("strategy_name"),
        "execution_reason": trade.get("execution_reason")
        or (trade.get("metadata") or {}).get("execution_reason"),
        "close_reason": trade.get("close_reason"),
        "confidence": trade.get("confidence"),
        "risk_pct": trade.get("risk_pct"),
        "exit_mode": trade.get("exit_mode"),
        "trade_date": trade_date,
        "metadata": trade.get("metadata") or {},
        "close_metadata": trade.get("close_metadata") or {},
        "raw_broker": trade.get("raw_broker"),
        "synced_at": trade.get("synced_at") or now,
        "created_at": trade.get("created_at") or now,
        "updated_at": now,
    }
    return doc


def overlay_only_when_state_conflicts(
    lot: dict[str, Any],
    trade: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    """When broker sync state disagrees with legacy status, keep broker state."""
    lot_state = _resolve_lot_state(lot)
    trade_state = _resolve_lot_state(trade)
    if lot.get("raw_broker") and lot_state != trade_state:
        return {k: v for k, v in overlay.items() if k in _OVERLAY_FIELDS}
    return overlay
