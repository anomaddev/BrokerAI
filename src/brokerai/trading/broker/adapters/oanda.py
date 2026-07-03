from __future__ import annotations

from dataclasses import asdict
from typing import Any

from brokerai.integrations.oanda import (
    close_broker_trade,
    extract_broker_trade_id,
    forex_pair_to_instrument,
    get_broker_open_trades_snapshot,
    list_all_trades,
    list_pending_orders,
    list_positions,
    list_transactions_idrange,
    list_transactions_since,
    parse_oanda_close_response,
    place_market_order,
    _parse_broker_timestamp,
)
from brokerai.trading.broker.adapters.base import BrokerAdapter
from brokerai.trading.broker.models import (
    BrokerEvent,
    ChildOrder,
    ExposureMismatch,
    PositionLot,
    SyncEventsResult,
)
from brokerai.trading.types import TradeIntent

OANDA_EXCHANGE_ID = "oanda"
DEFAULT_ASSET_CLASS = "forex"


def _child_order_from_normalized(raw: dict[str, Any] | None) -> ChildOrder | None:
    if not raw:
        return None
    return ChildOrder(
        broker_order_id=str(raw.get("broker_order_id", "")),
        order_type=str(raw.get("order_type", "")),
        state=str(raw.get("state", "")),
        price=raw.get("price"),
        trade_id=raw.get("trade_id"),
        create_time=_parse_broker_timestamp(raw.get("create_time")),
        filled_time=_parse_broker_timestamp(raw.get("filled_time")),
        filling_event_id=raw.get("filling_event_id"),
        cancelling_event_id=raw.get("cancelling_event_id"),
    )


def lot_from_oanda_trade(
    raw: dict[str, Any],
    *,
    exchange_id: str,
    account_id: str,
    asset_class: str = DEFAULT_ASSET_CLASS,
    overlay: dict[str, Any] | None = None,
) -> PositionLot:
    """Map normalized OANDA trade dict to ``PositionLot``."""
    overlay = overlay or {}
    state_raw = str(raw.get("state", "OPEN")).upper()
    state = "closed" if state_raw == "CLOSED" else "open"
    direction = str(raw.get("direction", "long")).lower()
    instrument = str(raw.get("instrument", ""))
    costs: dict[str, float] = {}
    financing = raw.get("financing")
    if financing is not None:
        costs["financing"] = float(financing)

    stop_loss = _child_order_from_normalized(raw.get("stop_loss"))
    take_profit = _child_order_from_normalized(raw.get("take_profit"))

    return PositionLot(
        exchange_id=exchange_id,
        account_id=account_id,
        broker_lot_id=str(raw.get("id", "")),
        asset_class=asset_class,
        state=state,
        instrument=instrument,
        symbol=instrument,
        direction=direction,
        initial_qty=float(raw.get("initial_units") or raw.get("units") or 0),
        current_qty=float(raw.get("current_units") or raw.get("units") or 0),
        entry_price=float(raw.get("entry_price") or raw.get("price") or 0),
        exit_price=raw.get("exit_price"),
        unrealized_pl=raw.get("unrealized_pl"),
        realized_pl=raw.get("realized_pl"),
        costs=costs,
        open_time=_parse_broker_timestamp(raw.get("open_time")),
        close_time=_parse_broker_timestamp(raw.get("close_time")),
        stop_loss=stop_loss,
        take_profit=take_profit,
        stop_loss_price=stop_loss.price if stop_loss else overlay.get("stop_loss"),
        take_profit_price=take_profit.price if take_profit else overlay.get("take_profit"),
        closing_event_ids=list(raw.get("closing_event_ids") or []),
        strategy_id=overlay.get("strategy_id"),
        strategy_name=overlay.get("strategy_name"),
        execution_reason=overlay.get("execution_reason"),
        close_reason=overlay.get("close_reason"),
        confidence=overlay.get("confidence"),
        risk_pct=overlay.get("risk_pct"),
        exit_mode=overlay.get("exit_mode"),
        raw_broker=raw.get("raw"),
    )


def event_from_oanda_transaction(
    raw: dict[str, Any],
    *,
    exchange_id: str,
    account_id: str,
) -> BrokerEvent:
    return BrokerEvent(
        exchange_id=exchange_id,
        account_id=account_id,
        broker_event_id=str(raw.get("id", "")),
        event_type=str(raw.get("type", "")),
        time=_parse_broker_timestamp(raw.get("time")),
        batch_id=raw.get("batch_id"),
        request_id=raw.get("request_id"),
        broker_lot_id=raw.get("trade_id"),
        broker_order_id=raw.get("order_id"),
        instrument=str(raw.get("instrument")) if raw.get("instrument") else None,
        qty=raw.get("units"),
        price=raw.get("price"),
        pl=raw.get("pl"),
        reason=str(raw.get("reason")) if raw.get("reason") else None,
        raw=raw.get("raw"),
    )


class OandaAdapter:
    exchange_id = OANDA_EXCHANGE_ID

    def _creds(self, credentials: dict[str, Any]) -> tuple[str, str]:
        access_token = str(credentials.get("access_token") or "").strip()
        environment = str(credentials.get("environment") or "practice")
        return access_token, environment

    async def sync_lots(
        self,
        credentials: dict[str, Any],
        account_id: str,
        *,
        state: str | None = None,
    ) -> tuple[list[PositionLot], str | None]:
        access_token, environment = self._creds(credentials)
        if state:
            raw_trades, last_txn = await list_all_trades(
                access_token,
                environment,
                account_id,
                state=state,
            )
        else:
            open_trades, txn_open = await list_all_trades(
                access_token,
                environment,
                account_id,
                state="OPEN",
            )
            closed_trades, txn_closed = await list_all_trades(
                access_token,
                environment,
                account_id,
                state="CLOSED",
            )
            by_id = {raw["id"]: raw for raw in open_trades}
            for raw in closed_trades:
                by_id[raw["id"]] = raw
            raw_trades = list(by_id.values())
            last_txn = txn_closed or txn_open
            if txn_open and txn_closed:
                try:
                    last_txn = str(max(int(txn_open), int(txn_closed)))
                except ValueError:
                    last_txn = txn_closed or txn_open
        lots = [
            lot_from_oanda_trade(raw, exchange_id=self.exchange_id, account_id=account_id)
            for raw in raw_trades
        ]
        return lots, last_txn

    async def sync_events(
        self,
        credentials: dict[str, Any],
        account_id: str,
        *,
        since_cursor: str | None,
        full: bool = False,
    ) -> SyncEventsResult:
        access_token, environment = self._creds(credentials)
        events: list[BrokerEvent] = []
        last_event_id: str | None = None
        cursor = since_cursor

        if full or not since_cursor:
            from brokerai.integrations.oanda import get_account_summary, list_positions

            _, positions_last = await list_positions(access_token, environment, account_id)
            end_id = positions_last or since_cursor or "1"
            start_id = "1"
            if since_cursor and since_cursor.isdigit() and int(since_cursor) > 0:
                start_id = since_cursor

            raw_events, cursor = await list_transactions_idrange(
                access_token,
                environment,
                account_id,
                from_id=start_id,
                to_id=end_id,
            )
            for raw in raw_events:
                events.append(
                    event_from_oanda_transaction(
                        raw,
                        exchange_id=self.exchange_id,
                        account_id=account_id,
                    )
                )
            if raw_events:
                last_event_id = raw_events[-1]["id"]
        elif since_cursor:
            raw_events, cursor = await list_transactions_since(
                access_token,
                environment,
                account_id,
                since_id=since_cursor,
            )
            for raw in raw_events:
                events.append(
                    event_from_oanda_transaction(
                        raw,
                        exchange_id=self.exchange_id,
                        account_id=account_id,
                    )
                )
            if raw_events:
                last_event_id = raw_events[-1]["id"]

        return SyncEventsResult(events=events, cursor=cursor, last_event_id=last_event_id)

    async def validate_exposure(
        self,
        credentials: dict[str, Any],
        account_id: str,
        lots: list[PositionLot],
    ) -> list[ExposureMismatch]:
        access_token, environment = self._creds(credentials)
        positions, _ = await list_positions(access_token, environment, account_id)
        mismatches: list[ExposureMismatch] = []

        local_by_key: dict[tuple[str, str], float] = {}
        for lot in lots:
            if lot.state != "open":
                continue
            key = (lot.symbol, lot.direction)
            local_by_key[key] = local_by_key.get(key, 0.0) + lot.current_qty

        broker_by_key: dict[tuple[str, str], float] = {}
        for pos in positions:
            instrument = str(pos.get("instrument", ""))
            for side in ("long", "short"):
                leg = pos.get(side) or {}
                try:
                    units = float(leg.get("units") or 0)
                except (TypeError, ValueError):
                    units = 0.0
                if units == 0:
                    continue
                direction = side
                broker_by_key[(instrument, direction)] = abs(units)

        all_keys = set(local_by_key) | set(broker_by_key)
        for key in all_keys:
            symbol, direction = key
            local_qty = local_by_key.get(key, 0.0)
            broker_qty = broker_by_key.get(key, 0.0)
            if abs(local_qty - broker_qty) > 0.01:
                mismatches.append(
                    ExposureMismatch(
                        symbol=symbol,
                        direction=direction,
                        local_qty=local_qty,
                        broker_qty=broker_qty,
                        message=f"Local qty {local_qty} != broker qty {broker_qty}",
                    )
                )
        return mismatches

    async def place_from_intent(
        self,
        credentials: dict[str, Any],
        account_id: str,
        intent: TradeIntent,
    ) -> tuple[PositionLot, dict[str, Any]]:
        access_token, environment = self._creds(credentials)
        units = intent.units if intent.units is not None else 1000.0
        if intent.direction == "short" and units > 0:
            units = -units
        elif intent.direction == "long" and units < 0:
            units = abs(units)

        instrument = forex_pair_to_instrument(intent.pair)
        response = await place_market_order(
            access_token,
            environment,
            account_id,
            instrument,
            units=units,
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit,
        )
        broker_lot_id = extract_broker_trade_id(response) or ""
        overlay = {
            **asdict(intent),
            "execution_reason": intent.metadata.get("execution_reason") if intent.metadata else None,
        }
        if broker_lot_id:
            from brokerai.integrations.oanda import get_broker_trade

            raw = await get_broker_trade(access_token, environment, account_id, broker_lot_id)
            if raw:
                lot = lot_from_oanda_trade(
                    raw,
                    exchange_id=self.exchange_id,
                    account_id=account_id,
                    asset_class=intent.asset_class,
                    overlay=overlay,
                )
                return lot, response

        lot = PositionLot(
            exchange_id=self.exchange_id,
            account_id=account_id,
            broker_lot_id=broker_lot_id,
            asset_class=intent.asset_class,
            state="open",
            instrument=instrument,
            symbol=instrument,
            direction=intent.direction,
            initial_qty=abs(units),
            current_qty=abs(units),
            entry_price=intent.entry_price,
            stop_loss_price=intent.stop_loss,
            take_profit_price=intent.take_profit,
            strategy_id=intent.strategy_id,
            strategy_name=intent.strategy_name,
            execution_reason=overlay.get("execution_reason"),
            confidence=intent.confidence,
            risk_pct=intent.risk_pct,
            exit_mode=intent.exit_mode,
        )
        return lot, response

    async def close_lot(
        self,
        credentials: dict[str, Any],
        account_id: str,
        broker_lot_id: str,
    ) -> tuple[PositionLot, dict[str, Any]]:
        access_token, environment = self._creds(credentials)
        response = await close_broker_trade(
            access_token,
            environment,
            account_id,
            broker_lot_id,
        )
        parsed = parse_oanda_close_response(response)
        from brokerai.integrations.oanda import get_broker_trade

        raw = await get_broker_trade(access_token, environment, account_id, broker_lot_id)
        if raw:
            lot = lot_from_oanda_trade(
                raw,
                exchange_id=self.exchange_id,
                account_id=account_id,
            )
            lot.state = "closed"
            lot.exit_price = parsed.get("exit_price")
            lot.realized_pl = parsed.get("realized_pl")
            lot.close_time = parsed.get("closed_at")
            return lot, response

        lot = PositionLot(
            exchange_id=self.exchange_id,
            account_id=account_id,
            broker_lot_id=broker_lot_id,
            asset_class=DEFAULT_ASSET_CLASS,
            state="closed",
            instrument="",
            symbol="",
            direction="long",
            initial_qty=0,
            current_qty=0,
            entry_price=0,
            exit_price=parsed.get("exit_price"),
            realized_pl=parsed.get("realized_pl"),
            close_time=parsed.get("closed_at"),
        )
        return lot, response

    async def fetch_open_lots_with_prices(
        self,
        credentials: dict[str, Any],
        account_id: str,
    ) -> list[PositionLot]:
        access_token, environment = self._creds(credentials)
        snapshot = await get_broker_open_trades_snapshot(access_token, environment, account_id)
        lots: list[PositionLot] = []
        for trade in snapshot["trades"]:
            raw = {
                **trade,
                "state": "OPEN",
                "initial_units": trade.get("initial_units") or trade.get("units"),
                "current_units": trade.get("current_units") or trade.get("units"),
                "entry_price": trade.get("entry_price") or trade.get("price"),
            }
            lot = lot_from_oanda_trade(
                raw,
                exchange_id=self.exchange_id,
                account_id=account_id,
            )
            lot.unrealized_pl = trade.get("unrealized_pl")
            lots.append(lot)
        return lots

    async def list_pending_orders(
        self,
        credentials: dict[str, Any],
        account_id: str,
    ) -> list[dict[str, Any]]:
        access_token, environment = self._creds(credentials)
        return await list_pending_orders(access_token, environment, account_id)
