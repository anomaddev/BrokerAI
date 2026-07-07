from __future__ import annotations

import logging
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
    normalize_oanda_transaction,
    parse_oanda_close_response,
    place_market_order,
    poll_account_changes,
    _parse_broker_timestamp,
)
from brokerai.trading.broker.adapters.base import BrokerAdapter
from brokerai.trading.broker.models import (
    BrokerEvent,
    ChildOrder,
    ExposureMismatch,
    PositionLot,
    SyncEventsResult,
    SyncPollResult,
)
from brokerai.trading.oanda_account_state import (
    apply_account_changes,
    detect_transaction_gap,
    open_lots_from_account_state,
    _apply_child_order_patches,
)
from brokerai.trading.types import TradeIntent

OANDA_EXCHANGE_ID = "oanda"
DEFAULT_ASSET_CLASS = "forex"

logger = logging.getLogger(__name__)


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
        full_bootstrap: bool = False,
    ) -> tuple[list[PositionLot], str | None]:
        access_token, environment = self._creds(credentials)
        if full_bootstrap and not state:
            from brokerai.trading.oanda_bootstrap import run_oanda_bootstrap

            bootstrap = await run_oanda_bootstrap(
                access_token,
                environment,
                account_id,
                exchange_id=self.exchange_id,
            )
            return bootstrap.lots, bootstrap.last_transaction_id

        if state:
            raw_trades, last_txn = await list_all_trades(
                access_token,
                environment,
                account_id,
                state=state,
            )
            lots = [
                lot_from_oanda_trade(raw, exchange_id=self.exchange_id, account_id=account_id)
                for raw in raw_trades
            ]
            return lots, last_txn

        raise ValueError(
            "OandaAdapter.sync_lots requires full_bootstrap=True or an explicit state filter; "
            "use run_oanda_bootstrap or sync_incremental_from_changes for cursor-driven sync."
        )

    async def sync_events(
        self,
        credentials: dict[str, Any],
        account_id: str,
        *,
        since_cursor: str | None,
        full: bool = False,
        transaction_end_id: str | None = None,
    ) -> SyncEventsResult:
        access_token, environment = self._creds(credentials)
        events: list[BrokerEvent] = []
        last_event_id: str | None = None
        cursor = since_cursor

        if full or not since_cursor:
            end_id = transaction_end_id or since_cursor or "1"
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
                normalized = normalize_oanda_transaction(raw)
                if normalized is None:
                    continue
                events.append(
                    event_from_oanda_transaction(
                        normalized,
                        exchange_id=self.exchange_id,
                        account_id=account_id,
                    )
                )
            if raw_events:
                last_event_id = str(raw_events[-1].get("id", ""))
        elif since_cursor:
            raw_events, cursor = await list_transactions_since(
                access_token,
                environment,
                account_id,
                since_id=since_cursor,
            )
            for raw in raw_events:
                normalized = normalize_oanda_transaction(raw)
                if normalized is None:
                    continue
                events.append(
                    event_from_oanda_transaction(
                        normalized,
                        exchange_id=self.exchange_id,
                        account_id=account_id,
                    )
                )
            if raw_events:
                last_event_id = str(raw_events[-1].get("id", ""))

        return SyncEventsResult(events=events, cursor=cursor, last_event_id=last_event_id)

    async def sync_incremental_from_changes(
        self,
        credentials: dict[str, Any],
        account_id: str,
        *,
        since_cursor: str,
    ) -> SyncPollResult:
        """Incremental sync via OANDA Poll Account Updates (single API call)."""
        access_token, environment = self._creds(credentials)
        poll = await poll_account_changes(
            access_token,
            environment,
            account_id,
            since_transaction_id=since_cursor,
        )
        changes = poll.get("changes") or {}
        repair_triggered = False
        applied = apply_account_changes(
            changes,
            exchange_id=self.exchange_id,
            account_id=account_id,
        )
        events: list[BrokerEvent] = list(applied.events)

        raw_txns = changes.get("transactions") or []
        if detect_transaction_gap(
            raw_txns,
            since_id=since_cursor,
            last_transaction_id=poll.get("lastTransactionID"),
        ):
            repair_triggered = True
            from brokerai.trading.oanda_cursor_repair import repair_transaction_gap

            gap_events = await repair_transaction_gap(
                access_token=access_token,
                environment=environment,
                account_id=account_id,
                exchange_id=self.exchange_id,
                since_cursor=since_cursor,
            )
            events.extend(gap_events)

        poll_state = poll.get("state") or {}
        state_trades = poll_state.get("trades") or []
        live_open_lots = open_lots_from_account_state(
            poll_state,
            exchange_id=self.exchange_id,
            account_id=account_id,
        )
        # OANDA AccountChanges state.trades are often TradeSummary stubs (id + PL only,
        # no instrument). Reconciliation needs full open trades — fetch when parsing
        # cannot build a lot for every trade listed in state.
        if state_trades and len(live_open_lots) < len(state_trades):
            fetched = await self.fetch_open_lots_with_prices(credentials, account_id)
            if fetched:
                live_open_lots = fetched
        if not live_open_lots:
            live_open_lots = [lot for lot in applied.lots if lot.state == "open"]
        else:
            _apply_child_order_patches(live_open_lots, applied.child_order_patches)

        return SyncPollResult(
            lots=applied.lots,
            events=events,
            live_open_lots=live_open_lots,
            cursor=poll.get("lastTransactionID"),
            repair_triggered=repair_triggered,
            poll_state=poll.get("state") or {},
        )

    async def validate_exposure(
        self,
        credentials: dict[str, Any],
        account_id: str,
        lots: list[PositionLot] | None = None,
    ) -> list[ExposureMismatch]:
        access_token, environment = self._creds(credentials)
        positions, _ = await list_positions(access_token, environment, account_id)
        mismatches: list[ExposureMismatch] = []

        from brokerai.db.repositories.instrument_exposure import InstrumentExposureRepository

        exposure_repo = InstrumentExposureRepository()
        rollups = await exposure_repo.list_for_account(
            exchange_id=self.exchange_id,
            account_id=account_id,
        )
        if rollups:
            local_by_key = InstrumentExposureRepository.rollups_to_local_by_key(rollups)
        else:
            local_by_key = {}
            source_lots = lots or []
            for lot in source_lots:
                if lot.state != "open":
                    continue
                key = (lot.symbol, lot.direction)
                local_by_key[key] = local_by_key.get(key, 0.0) + lot.current_qty
            if not local_by_key:
                from brokerai.db.repositories.broker_lots import BrokerLotsRepository

                open_docs = await BrokerLotsRepository().list_open_lots(
                    exchange_id=self.exchange_id,
                )
                for lot_doc in open_docs:
                    if str(lot_doc.get("account_id") or "") not in ("", account_id):
                        continue
                    symbol = str(lot_doc.get("symbol") or lot_doc.get("instrument") or "")
                    direction = str(lot_doc.get("direction") or "long").lower()
                    key = (symbol, direction)
                    local_by_key[key] = local_by_key.get(key, 0.0) + float(
                        lot_doc.get("current_qty") or 0
                    )

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

    @staticmethod
    def _log_fill_slippage(intent: TradeIntent, lot: PositionLot) -> None:
        """Log signal-vs-fill slippage so entry-outside-candle drift is diagnosable.

        ``intent.entry_price`` is the signal candle close; ``lot.entry_price`` is the
        actual broker fill (ask for longs / bid for shorts). The difference is spread +
        latency slippage and is exactly what makes fills land outside a mid candle.
        """
        try:
            from brokerai.trading.risk_intent import pip_size_for_pair

            intended = float(intent.entry_price or 0)
            fill = float(lot.entry_price or 0)
            pip = pip_size_for_pair(intent.pair) or 0.0001
            slip_pips = (fill - intended) / pip if intended else 0.0
            logger.info(
                "FILL slippage lot=%s pair=%s dir=%s intended=%.5f fill=%.5f "
                "slip_pips=%.2f signal_candle=%s",
                lot.broker_lot_id,
                intent.pair,
                intent.direction,
                intended,
                fill,
                slip_pips,
                (intent.metadata or {}).get("entry_candle_open"),
            )
        except Exception:  # never let diagnostics break order placement
            logger.debug("Fill slippage logging failed", exc_info=True)

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
                lot.signal_entry_price = intent.entry_price
                self._log_fill_slippage(intent, lot)
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
