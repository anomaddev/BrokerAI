from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from brokerai.integrations.oanda import _parse_broker_timestamp
from brokerai.trading.broker.sync import run_broker_sync

logger = logging.getLogger(__name__)

SYNC_STRATEGY_ID = "oanda-import"
SYNC_STRATEGY_NAME = "OANDA Import"
SYNC_METADATA_SOURCE = "oanda_sync"
BROKER_CLOSED_REASON = "broker_closed"


def _parse_broker_open_time(raw: str | None) -> datetime | None:
    """Backward-compatible alias for OANDA timestamp parsing."""
    return _parse_broker_timestamp(raw)


def broker_closed_trade_to_ledger_close(broker_trade: dict[str, Any]) -> dict[str, Any]:
    """Build ledger close kwargs from a normalized OANDA closed trade."""
    metadata: dict[str, Any] = {
        "source": SYNC_METADATA_SOURCE,
        "broker_trade_id": broker_trade.get("id"),
    }
    if broker_trade.get("open_time"):
        metadata["broker_open_time"] = broker_trade["open_time"]
    if broker_trade.get("close_time"):
        metadata["broker_close_time"] = broker_trade["close_time"]

    return {
        "reason": BROKER_CLOSED_REASON,
        "metadata": metadata,
        "exit_price": broker_trade.get("exit_price"),
        "realized_pl": broker_trade.get("realized_pl"),
        "closed_at": broker_trade.get("closed_at"),
    }


def broker_trade_to_ledger_intent(broker_trade: dict[str, Any]) -> dict[str, Any]:
    """Build a ledger trade payload from a normalized OANDA open trade."""
    direction = str(broker_trade.get("direction", "long")).lower()
    units = float(broker_trade.get("units") or 0)
    if direction == "short":
        units = -abs(units)
    else:
        units = abs(units)

    broker_id = str(broker_trade.get("id", ""))
    open_time = broker_trade.get("open_time")
    metadata: dict[str, Any] = {"source": SYNC_METADATA_SOURCE, "execution_reason": "oanda_import"}
    if open_time:
        metadata["broker_open_time"] = open_time

    return {
        "strategy_id": SYNC_STRATEGY_ID,
        "strategy_name": SYNC_STRATEGY_NAME,
        "pair": broker_trade.get("pair"),
        "asset_class": "forex",
        "direction": direction,
        "entry_price": broker_trade.get("price") or broker_trade.get("entry_price"),
        "stop_loss": None,
        "take_profit": None,
        "exit_mode": "manual",
        "risk_pct": 0.0,
        "units": units,
        "confidence": 0.0,
        "metadata": metadata,
        "broker_order_id": broker_id,
        "opened_at": _parse_broker_open_time(str(open_time) if open_time else None),
    }


async def sync_oanda_trades_to_ledger(*, force: bool = False) -> dict[str, Any]:
    """Import/sync OANDA state into ``broker_lots`` via the unified broker sync."""
    result = await run_broker_sync(exchange_id="oanda", mode="incremental", force=force)
    payload = result.to_dict()
    payload.setdefault("imported_trade_ids", [])
    payload.setdefault("updated_trade_ids", [])
    payload.setdefault("closed_trade_ids", [])
    payload["backfilled_trade_ids"] = list(result.backfilled_lot_ids)
    payload["skipped"] = 1 if result.skipped_reason else 0
    payload["backfilled"] = result.backfilled
    return payload
