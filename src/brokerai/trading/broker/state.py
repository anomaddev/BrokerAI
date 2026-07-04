from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.db.repositories.broker_events import BrokerEventsRepository
from brokerai.db.repositories.broker_lots import BrokerLotsRepository, apply_candle_anchors_to_lot, serialize_lot
from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository, OANDA_ID
from brokerai.db.repositories.instrument_exposure import InstrumentExposureRepository
from brokerai.trading.broker.adapters.base import get_adapter
from brokerai.trading.broker.models import InstrumentExposure, PositionLot, SyncMode, SyncResult
from brokerai.trading.broker.sync import run_broker_sync
from brokerai.trading.types import TradeIntent


class BrokerNotConfiguredError(Exception):
    """Raised when broker credentials are missing for an exchange."""


class BrokerStateService:
    """Single bot entry point for broker state."""

    def __init__(
        self,
        lots_repo: BrokerLotsRepository | None = None,
        events_repo: BrokerEventsRepository | None = None,
    ) -> None:
        self._lots = lots_repo or BrokerLotsRepository()
        self._events = events_repo or BrokerEventsRepository()

    async def _credentials_for(
        self,
        exchange_id: str,
    ) -> tuple[dict[str, Any], str] | tuple[None, None]:
        conn = await ExchangeConnectionsRepository().get_connection(exchange_id)
        if exchange_id == OANDA_ID:
            access_token = str(conn.get("access_token") or "").strip()
            account_id = str(conn.get("account_id") or "").strip()
            if not access_token or not account_id:
                return None, None
            return {
                "access_token": access_token,
                "environment": str(conn.get("environment") or "practice"),
            }, account_id
        return None, None

    async def _oanda_context(self) -> tuple[dict[str, Any], str] | tuple[None, None]:
        return await self._credentials_for(OANDA_ID)

    async def sync(
        self,
        exchange_id: str = "oanda",
        *,
        mode: SyncMode = "incremental",
        force: bool = False,
    ) -> SyncResult:
        return await run_broker_sync(exchange_id=exchange_id, mode=mode, force=force)

    async def get_open_lots(
        self,
        *,
        exchange_id: str = "oanda",
        strategy_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._lots.list_open_lots(exchange_id=exchange_id, strategy_id=strategy_id)

    async def get_lot(self, exchange_id: str, broker_lot_id: str) -> dict[str, Any] | None:
        credentials, account_id = await self._credentials_for(exchange_id)
        if credentials is None or account_id is None:
            return None
        return await self._lots.get_by_broker_lot_id(exchange_id, account_id, broker_lot_id)

    async def get_lot_by_id(self, lot_id: str) -> dict[str, Any] | None:
        return await self._lots.get_by_id(lot_id)

    async def place_from_intent(
        self,
        exchange_id: str,
        intent: TradeIntent,
    ) -> dict[str, Any]:
        credentials, account_id = await self._credentials_for(exchange_id)
        intent_meta = intent.metadata or {}
        if credentials is None or account_id is None:
            lot = PositionLot(
                exchange_id=exchange_id,
                account_id="paper",
                broker_lot_id="",
                asset_class=intent.asset_class,
                state="open",
                instrument=intent.pair.replace("/", "_"),
                symbol=intent.pair.replace("/", "_"),
                direction=intent.direction,
                initial_qty=abs(intent.units or 1000),
                current_qty=abs(intent.units or 1000),
                entry_price=intent.entry_price,
                signal_entry_price=intent.entry_price,
                stop_loss_price=intent.stop_loss,
                take_profit_price=intent.take_profit,
                strategy_id=intent.strategy_id,
                strategy_name=intent.strategy_name,
                execution_reason=intent_meta.get("execution_reason"),
                confidence=intent.confidence,
                risk_pct=intent.risk_pct,
                exit_mode=intent.exit_mode,
                timeframe=intent_meta.get("timeframe"),
                entry_candle_open=intent_meta.get("entry_candle_open"),
                id=uuid4().hex,
                open_time=datetime.now(timezone.utc),
            )
            apply_candle_anchors_to_lot(lot, strategy_timeframe=intent_meta.get("timeframe"))
            return await self._lots.upsert_lot(lot, preserve_overlay=False)

        adapter = get_adapter(exchange_id)
        lot, _response = await adapter.place_from_intent(credentials, account_id, intent)
        lot.id = uuid4().hex
        lot.signal_entry_price = intent.entry_price
        lot.strategy_id = intent.strategy_id
        lot.strategy_name = intent.strategy_name
        lot.execution_reason = intent_meta.get("execution_reason")
        lot.confidence = intent.confidence
        lot.risk_pct = intent.risk_pct
        lot.exit_mode = intent.exit_mode
        lot.stop_loss_price = intent.stop_loss
        lot.take_profit_price = intent.take_profit
        lot.timeframe = intent_meta.get("timeframe")
        lot.entry_candle_open = intent_meta.get("entry_candle_open")
        apply_candle_anchors_to_lot(lot, strategy_timeframe=intent_meta.get("timeframe"))
        saved = await self._lots.upsert_lot(lot, preserve_overlay=False)
        await run_broker_sync(exchange_id=exchange_id, mode="incremental", force=True)
        return saved

    async def close_lot(
        self,
        exchange_id: str,
        lot_id: str,
        *,
        reason: str,
        close_metadata: dict[str, Any] | None = None,
        exit_candle_open: str | None = None,
    ) -> dict[str, Any] | None:
        lot_doc = await self._lots.get_by_id(lot_id)
        if lot_doc is None:
            return None
        if lot_doc.get("state") != "open":
            return lot_doc

        broker_lot_id = str(lot_doc.get("broker_lot_id") or "")
        credentials, account_id = await self._credentials_for(exchange_id)
        close_metadata = dict(close_metadata or {})
        exit_candle = exit_candle_open or close_metadata.pop("exit_candle_open", None)

        if credentials and account_id and broker_lot_id:
            adapter = get_adapter(exchange_id)
            closed_lot, response = await adapter.close_lot(credentials, account_id, broker_lot_id)
            close_metadata["broker_close"] = response
            closed_lot.id = lot_doc.get("id")
            closed_lot.close_reason = reason
            closed_lot.strategy_id = lot_doc.get("strategy_id")
            closed_lot.strategy_name = lot_doc.get("strategy_name")
            closed_lot.timeframe = closed_lot.timeframe or lot_doc.get("timeframe")
            closed_lot.entry_candle_open = closed_lot.entry_candle_open or lot_doc.get("entry_candle_open")
            if exit_candle:
                closed_lot.exit_candle_open = exit_candle
            apply_candle_anchors_to_lot(
                closed_lot,
                strategy_timeframe=closed_lot.timeframe or lot_doc.get("timeframe"),
            )
            saved = await self._lots.upsert_lot(closed_lot, preserve_overlay=True)
            if close_metadata:
                await self._lots.apply_strategy_overlay(
                    exchange_id,
                    str(lot_doc.get("account_id") or account_id),
                    broker_lot_id,
                    {"close_metadata": close_metadata},
                )
            await run_broker_sync(exchange_id=exchange_id, mode="incremental", force=True)
            return saved

        await self._lots.close_lot(
            lot_id,
            reason=reason,
            exit_candle_open=exit_candle,
            close_metadata=close_metadata or None,
        )
        return await self._lots.get_by_id(lot_id)

    async def get_instrument_exposure(
        self,
        exchange_id: str,
        symbol: str,
        *,
        direction: str | None = None,
    ) -> InstrumentExposure | None:
        credentials, account_id = await self._credentials_for(exchange_id)
        if account_id:
            materialized = await InstrumentExposureRepository().get_for_symbol(
                exchange_id=exchange_id,
                account_id=account_id,
                symbol=symbol,
                direction=direction,
            )
            if materialized is not None:
                return materialized

        lots = await self._lots.list_open_lots(exchange_id=exchange_id)
        matching = [
            lot
            for lot in lots
            if lot.get("symbol") == symbol or lot.get("pair") == symbol.replace("_", "/")
        ]
        if direction:
            matching = [lot for lot in matching if str(lot.get("direction") or "").lower() == direction.lower()]
        if not matching:
            return None
        resolved_direction = str(matching[0].get("direction", "long"))
        total_qty = sum(float(lot.get("current_qty") or 0) for lot in matching)
        total_pl = sum(
            float(lot.get("unrealized_pl") or 0)
            for lot in matching
            if lot.get("unrealized_pl") is not None
        )
        weighted_price = 0.0
        if total_qty > 0:
            weighted_price = sum(
                float(lot.get("entry_price") or 0) * float(lot.get("current_qty") or 0)
                for lot in matching
            ) / total_qty
        return InstrumentExposure(
            exchange_id=exchange_id,
            symbol=symbol,
            direction=resolved_direction,
            total_qty=total_qty,
            average_price=weighted_price,
            unrealized_pl=total_pl if total_pl else None,
            broker_lot_ids=[str(lot.get("broker_lot_id")) for lot in matching],
        )

    async def list_instrument_exposure(
        self,
        *,
        exchange_id: str = "oanda",
    ) -> list[dict[str, Any]]:
        credentials, account_id = await self._credentials_for(exchange_id)
        if account_id is None:
            return []
        rollups = await InstrumentExposureRepository().list_for_account(
            exchange_id=exchange_id,
            account_id=account_id,
        )
        if rollups:
            return rollups
        lots = await self._lots.list_open_lots(exchange_id=exchange_id)
        account_lots = [lot for lot in lots if str(lot.get("account_id") or "") == account_id]
        from brokerai.db.repositories.instrument_exposure import _rollup_from_lot_docs

        return [row.to_dict() for row in _rollup_from_lot_docs(account_lots, exchange_id=exchange_id)]

    async def get_events(
        self,
        *,
        exchange_id: str = "oanda",
        broker_lot_id: str | None = None,
    ) -> list[dict[str, Any]]:
        credentials, account_id = await self._credentials_for(exchange_id)
        return await self._events.list_events(
            exchange_id=exchange_id,
            account_id=account_id,
            broker_lot_id=broker_lot_id,
        )

    async def list_lots(self, **kwargs: Any) -> list[dict[str, Any]]:
        return await self._lots.list_lots(**kwargs)

    async def count_trades_today(self, strategy_id: str, pair: str) -> int:
        return await self._lots.count_lots_today(strategy_id, pair)

    async def daily_trade_counts(self) -> dict[tuple[str, str], int]:
        return await self._lots.daily_lot_counts()
