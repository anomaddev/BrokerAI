from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.db.repositories.broker_lots import (
    BrokerLotsRepository,
    _execution_reason_from_metadata,
    serialize_lot,
)
from brokerai.trading.broker.models import PositionLot
from brokerai.trading.types import TradeIntent


class TradesRepository:
    """Backward-compatible facade over ``BrokerLotsRepository``."""

    COLLECTION = "broker_lots"

    def __init__(self) -> None:
        self._lots = BrokerLotsRepository()

    async def create_open_trade(
        self,
        intent: dict[str, Any],
        *,
        broker_order_id: str | None = None,
        opened_at: datetime | None = None,
    ) -> dict[str, Any]:
        if broker_order_id:
            lot = PositionLot(
                exchange_id="oanda",
                account_id="",
                broker_lot_id=str(broker_order_id),
                asset_class=str(intent.get("asset_class", "forex")),
                state="open",
                instrument=str(intent.get("pair", "")).replace("/", "_"),
                symbol=str(intent.get("pair", "")).replace("/", "_"),
                direction=str(intent.get("direction", "long")),
                initial_qty=abs(float(intent.get("units") or 0)),
                current_qty=abs(float(intent.get("units") or 0)),
                entry_price=float(intent.get("entry_price") or 0),
                stop_loss_price=intent.get("stop_loss"),
                take_profit_price=intent.get("take_profit"),
                strategy_id=intent.get("strategy_id"),
                strategy_name=intent.get("strategy_name"),
                execution_reason=(intent.get("metadata") or {}).get("execution_reason"),
                confidence=intent.get("confidence"),
                risk_pct=intent.get("risk_pct"),
                exit_mode=intent.get("exit_mode"),
                id=uuid4().hex,
                open_time=opened_at or datetime.now(timezone.utc),
            )
            return await self._lots.upsert_lot(lot, preserve_overlay=False)

        from brokerai.trading.broker.state import BrokerStateService

        trade_intent = TradeIntent(**intent)
        return await BrokerStateService(lots_repo=self._lots).place_from_intent("oanda", trade_intent)

    async def get_open_by_broker_order_id(self, broker_order_id: str) -> dict[str, Any] | None:
        handle_lots = await self._lots.list_open_lots()
        for lot in handle_lots:
            if str(lot.get("broker_lot_id")) == str(broker_order_id):
                return lot
        return None

    async def update_broker_order_id(self, trade_id: str, broker_order_id: str) -> None:
        lot = await self._lots.get_by_id(trade_id)
        if lot is None:
            return
        await self._lots.apply_strategy_overlay(
            str(lot.get("exchange_id", "oanda")),
            str(lot.get("account_id", "")),
            str(lot.get("broker_lot_id", "")),
            {"broker_lot_id": broker_order_id, "broker_order_id": broker_order_id},
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
        from brokerai.trading.broker.state import BrokerStateService

        lot = await self._lots.get_by_id(trade_id)
        if lot is None:
            return
        exit_candle_open = (metadata or {}).get("exit_candle_open")
        if lot.get("state") == "open" and lot.get("broker_lot_id"):
            await BrokerStateService(lots_repo=self._lots).close_lot(
                str(lot.get("exchange_id", "oanda")),
                trade_id,
                reason=reason,
                close_metadata=metadata,
                exit_candle_open=exit_candle_open,
            )
            return
        await self._lots.close_lot(
            trade_id,
            reason=reason,
            exit_price=exit_price,
            realized_pl=realized_pl,
            closed_at=closed_at,
            exit_candle_open=exit_candle_open,
            close_metadata=metadata,
        )

    async def backfill_close_details(
        self,
        trade_id: str,
        *,
        exit_price: float | None = None,
        realized_pl: float | None = None,
        closed_at: datetime | None = None,
    ) -> bool:
        return await self._lots.backfill_close_details(
            trade_id,
            exit_price=exit_price,
            realized_pl=realized_pl,
            closed_at=closed_at,
        )

    async def list_closed_trades_missing_close_details(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return await self._lots.list_closed_lots_missing_close_details(limit=limit)

    async def get_by_id(self, trade_id: str) -> dict[str, Any] | None:
        return await self._lots.get_by_id(trade_id)

    async def list_trades(
        self,
        *,
        status: str = "open",
        strategy_id: str | None = None,
        pair: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        state = "all" if status == "all" else status
        return await self._lots.list_lots(
            state=state,
            strategy_id=strategy_id,
            pair=pair,
            limit=limit,
            before=before,
        )

    async def list_open_trades(self) -> list[dict[str, Any]]:
        return await self._lots.list_open_lots()

    async def count_trades_today(self, strategy_id: str, pair: str, *, on_date: date | None = None) -> int:
        return await self._lots.count_lots_today(strategy_id, pair, on_date=on_date)

    async def daily_trade_counts(self, *, on_date: date | None = None) -> dict[tuple[str, str], int]:
        return await self._lots.daily_lot_counts(on_date=on_date)


def serialize_trade(doc: dict[str, Any]) -> dict[str, Any]:
    return serialize_lot(doc)
