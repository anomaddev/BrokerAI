from __future__ import annotations

import logging
from dataclasses import asdict

from brokerai.bots.associate.assets.base import AssetAssociate
from brokerai.db.repositories.asset_settings import AssetSettingsRepository
from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.db.repositories.trades import TradesRepository
from brokerai.integrations.oanda import forex_pair_to_instrument, place_market_order
from brokerai.trading.schedule import utc_now
from brokerai.trading.session_gate import is_asset_trading_session_active
from brokerai.trading.types import TradeIntent

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNT_BALANCE = 10_000.0


class ForexAssociate(AssetAssociate):
    asset_class = "forex"

    def _estimate_units(self, intent: TradeIntent) -> float:
        if intent.units is not None:
            return intent.units
        if intent.stop_loss is None or intent.entry_price <= 0:
            return 1000.0

        risk_amount = DEFAULT_ACCOUNT_BALANCE * (intent.risk_pct / 100.0)
        stop_distance = abs(intent.entry_price - intent.stop_loss)
        if stop_distance <= 0:
            return 1000.0

        units = risk_amount / stop_distance
        if intent.direction == "short":
            units = -units
        return round(units, 0)

    async def place_order(self, payload: dict) -> None:
        intent = TradeIntent(**payload)
        settings = await AssetSettingsRepository().get("forex")
        if not settings.get("enabled"):
            logger.warning("Forex trading disabled — skipping order for %s", intent.pair)
            return

        if not is_asset_trading_session_active(settings.get("enabled_sessions"), when=utc_now()):
            logger.warning(
                "Forex trading outside enabled market sessions — skipping order for %s",
                intent.pair,
            )
            return

        oanda = await ExchangeConnectionsRepository().get_oanda()
        access_token = oanda.get("access_token") or ""
        environment = oanda.get("environment") or "practice"
        account_id = oanda.get("account_id") or ""
        if not access_token.strip() or not account_id.strip():
            logger.warning("OANDA not configured — logging intent only for %s", intent.pair)
            await TradesRepository().create_open_trade(asdict(intent))
            return

        units = self._estimate_units(intent)
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
        order_fill = response.get("orderFillTransaction") or response.get("orderCreateTransaction") or {}
        broker_order_id = str(order_fill.get("id", ""))
        trade_payload = asdict(intent)
        trade_payload["units"] = units
        await TradesRepository().create_open_trade(trade_payload, broker_order_id=broker_order_id)
        logger.info(
            "Forex associate placed order %s %s units=%s order_id=%s",
            intent.pair,
            intent.direction,
            units,
            broker_order_id,
        )
