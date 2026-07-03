from __future__ import annotations

"""Backward-compatible trade sync entry points.

The canonical implementation lives in ``brokerai.trading.broker.sync``.
"""

from brokerai.trading.broker.sync import run_broker_sync
from brokerai.trading.trade_sync import (
    BROKER_CLOSED_REASON,
    SYNC_METADATA_SOURCE,
    SYNC_STRATEGY_ID,
    SYNC_STRATEGY_NAME,
    _parse_broker_open_time,
    broker_closed_trade_to_ledger_close,
    broker_trade_to_ledger_intent,
    sync_oanda_trades_to_ledger,
)

__all__ = [
    "BROKER_CLOSED_REASON",
    "SYNC_METADATA_SOURCE",
    "SYNC_STRATEGY_ID",
    "SYNC_STRATEGY_NAME",
    "_parse_broker_open_time",
    "broker_closed_trade_to_ledger_close",
    "broker_trade_to_ledger_intent",
    "run_broker_sync",
    "sync_oanda_trades_to_ledger",
]
