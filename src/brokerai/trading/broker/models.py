from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

LotState = Literal["open", "closed", "cancelled"]
SyncMode = Literal["incremental", "full", "repair"]


@dataclass
class ChildOrder:
    """Normalized child order (stop-loss, take-profit, etc.)."""

    broker_order_id: str
    order_type: str
    state: str
    price: float | None = None
    trade_id: str | None = None
    create_time: datetime | None = None
    filled_time: datetime | None = None
    filling_event_id: str | None = None
    cancelling_event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker_order_id": self.broker_order_id,
            "order_type": self.order_type,
            "state": self.state,
            "price": self.price,
            "trade_id": self.trade_id,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "filled_time": self.filled_time.isoformat() if self.filled_time else None,
            "filling_event_id": self.filling_event_id,
            "cancelling_event_id": self.cancelling_event_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ChildOrder | None:
        if not raw:
            return None
        create_time = raw.get("create_time")
        filled_time = raw.get("filled_time")
        return cls(
            broker_order_id=str(raw.get("broker_order_id", "")),
            order_type=str(raw.get("order_type", "")),
            state=str(raw.get("state", "")),
            price=raw.get("price"),
            trade_id=raw.get("trade_id"),
            create_time=datetime.fromisoformat(create_time.replace("Z", "+00:00"))
            if isinstance(create_time, str)
            else create_time,
            filled_time=datetime.fromisoformat(filled_time.replace("Z", "+00:00"))
            if isinstance(filled_time, str)
            else filled_time,
            filling_event_id=raw.get("filling_event_id"),
            cancelling_event_id=raw.get("cancelling_event_id"),
        )


@dataclass
class PositionLot:
    """Exchange-agnostic atomic exposure unit (OANDA Trade, stock fill lot, etc.)."""

    exchange_id: str
    account_id: str
    broker_lot_id: str
    asset_class: str
    state: LotState
    instrument: str
    symbol: str
    direction: str
    initial_qty: float
    current_qty: float
    entry_price: float
    exit_price: float | None = None
    # Intended entry from the strategy signal candle (its close). ``entry_price``
    # is the actual broker fill (ask for longs, bid for shorts) and can differ by
    # spread + slippage; keeping both lets charts/analytics show the in-range
    # signal price and quantify real slippage.
    signal_entry_price: float | None = None
    unrealized_pl: float | None = None
    realized_pl: float | None = None
    costs: dict[str, float] = field(default_factory=dict)
    open_time: datetime | None = None
    close_time: datetime | None = None
    stop_loss: ChildOrder | None = None
    take_profit: ChildOrder | None = None
    closing_event_ids: list[str] = field(default_factory=list)
    entry_batch_id: str | None = None
    last_event_id: str | None = None
    strategy_id: str | None = None
    strategy_name: str | None = None
    execution_reason: str | None = None
    close_reason: str | None = None
    confidence: float | None = None
    risk_pct: float | None = None
    exit_mode: str | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    timeframe: str | None = None
    entry_candle_open: str | None = None
    exit_candle_open: str | None = None
    id: str | None = None
    trade_date: str | None = None
    synced_at: datetime | None = None
    raw_broker: dict[str, Any] | None = None

    @property
    def pair(self) -> str:
        """Display pair for forex/metals (EUR/USD from EUR_USD)."""
        if self.asset_class in ("forex", "metals"):
            return self.symbol.replace("_", "/")
        return self.symbol

    @property
    def units(self) -> float:
        """Signed units for bot compatibility (negative = short)."""
        qty = self.current_qty if self.state == "open" else self.initial_qty
        if self.direction == "short":
            return -abs(qty)
        return abs(qty)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "exchange_id": self.exchange_id,
            "account_id": self.account_id,
            "broker_lot_id": self.broker_lot_id,
            "asset_class": self.asset_class,
            "state": self.state,
            "instrument": self.instrument,
            "symbol": self.symbol,
            "pair": self.pair,
            "direction": self.direction,
            "initial_qty": self.initial_qty,
            "current_qty": self.current_qty,
            "units": self.units,
            "entry_price": self.entry_price,
            "signal_entry_price": self.signal_entry_price,
            "exit_price": self.exit_price,
            "unrealized_pl": self.unrealized_pl,
            "realized_pl": self.realized_pl,
            "costs": self.costs,
            "open_time": self.open_time.isoformat() if self.open_time else None,
            "close_time": self.close_time.isoformat() if self.close_time else None,
            "stop_loss": self.stop_loss.to_dict() if self.stop_loss else None,
            "take_profit": self.take_profit.to_dict() if self.take_profit else None,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "closing_event_ids": self.closing_event_ids,
            "entry_batch_id": self.entry_batch_id,
            "last_event_id": self.last_event_id,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "execution_reason": self.execution_reason,
            "close_reason": self.close_reason,
            "confidence": self.confidence,
            "risk_pct": self.risk_pct,
            "exit_mode": self.exit_mode,
            "timeframe": self.timeframe,
            "entry_candle_open": self.entry_candle_open,
            "exit_candle_open": self.exit_candle_open,
            "trade_date": self.trade_date,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
        }


@dataclass
class BrokerEvent:
    """Immutable broker audit event (OANDA transaction, stock fill, etc.)."""

    exchange_id: str
    account_id: str
    broker_event_id: str
    event_type: str
    time: datetime | None
    batch_id: str | None = None
    request_id: str | None = None
    broker_lot_id: str | None = None
    broker_order_id: str | None = None
    instrument: str | None = None
    qty: float | None = None
    price: float | None = None
    pl: float | None = None
    reason: str | None = None
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange_id": self.exchange_id,
            "account_id": self.account_id,
            "broker_event_id": self.broker_event_id,
            "event_type": self.event_type,
            "time": self.time.isoformat() if self.time else None,
            "batch_id": self.batch_id,
            "request_id": self.request_id,
            "broker_lot_id": self.broker_lot_id,
            "broker_order_id": self.broker_order_id,
            "instrument": self.instrument,
            "qty": self.qty,
            "price": self.price,
            "pl": self.pl,
            "reason": self.reason,
        }


@dataclass
class InstrumentExposure:
    """Computed rollup for one instrument/side."""

    exchange_id: str
    symbol: str
    direction: str
    total_qty: float
    average_price: float | None
    unrealized_pl: float | None
    broker_lot_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange_id": self.exchange_id,
            "symbol": self.symbol,
            "pair": self.symbol.replace("_", "/"),
            "direction": self.direction,
            "total_qty": self.total_qty,
            "average_price": self.average_price,
            "unrealized_pl": self.unrealized_pl,
            "broker_lot_ids": self.broker_lot_ids,
        }


@dataclass
class ExposureMismatch:
    symbol: str
    direction: str
    local_qty: float
    broker_qty: float
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "local_qty": self.local_qty,
            "broker_qty": self.broker_qty,
            "message": self.message,
        }


@dataclass
class SyncPollResult:
    lots: list[PositionLot]
    events: list[BrokerEvent]
    live_open_lots: list[PositionLot]
    cursor: str | None
    repair_triggered: bool = False
    poll_state: dict[str, Any] | None = None


@dataclass
class SyncEventsResult:
    events: list[BrokerEvent]
    cursor: str | None
    last_event_id: str | None = None


@dataclass
class SyncResult:
    configured: bool
    mode: SyncMode
    lots_upserted: int = 0
    events_upserted: int = 0
    lots_closed: int = 0
    enriched: int = 0
    backfilled: int = 0
    backfilled_lot_ids: list[str] = field(default_factory=list)
    exposure_mismatches: list[ExposureMismatch] = field(default_factory=list)
    summary_synced: bool = False
    repair_triggered: bool = False
    account_id: str | None = None
    cursor_before: str | None = None
    cursor_after: str | None = None
    changes_applied: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "mode": self.mode,
            "lots_upserted": self.lots_upserted,
            "events_upserted": self.events_upserted,
            "lots_closed": self.lots_closed,
            "enriched": self.enriched,
            "backfilled": self.backfilled,
            "backfilled_lot_ids": list(self.backfilled_lot_ids),
            "exposure_mismatches": [m.to_dict() for m in self.exposure_mismatches],
            "summary_synced": self.summary_synced,
            "repair_triggered": self.repair_triggered,
            "account_id": self.account_id,
            "cursor_before": self.cursor_before,
            "cursor_after": self.cursor_after,
            "changes_applied": dict(self.changes_applied),
            "error": self.error,
            "skipped_reason": self.skipped_reason,
            "imported": self.lots_upserted,
            "updated": self.enriched,
            "closed": self.lots_closed,
        }
