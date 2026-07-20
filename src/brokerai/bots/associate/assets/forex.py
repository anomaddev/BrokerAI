from __future__ import annotations

import logging
from dataclasses import asdict

from brokerai.bots.associate.assets.base import AssetAssociate
from brokerai.bots.data_manager.candle_requirements import strategy_params
from brokerai.db.repositories.asset_settings import AssetSettingsRepository, enabled_forex_pairs
from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.trading.broker.state import BrokerStateService
from brokerai.trading.schedule import utc_now
from brokerai.trading.session_hold import (
    effective_session_ids,
    is_effective_session_coverage,
)
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

        allowed_pairs = set(enabled_forex_pairs(list(settings.get("enabled_pairs") or [])))
        if intent.pair not in allowed_pairs:
            logger.warning(
                "Forex pair %s not enabled globally — skipping order",
                intent.pair,
            )
            return

        now = utc_now()
        strategy = await StrategiesRepository().get_by_id(intent.strategy_id)
        if strategy is None:
            logger.warning(
                "Strategy %s not found — skipping order for %s",
                intent.strategy_id,
                intent.pair,
            )
            return
        params = strategy_params(strategy)
        effective = effective_session_ids(settings.get("enabled_sessions"), params)
        if not effective or not is_effective_session_coverage(now, effective):
            logger.warning(
                "Forex trading outside effective sessions (global∩strategy) — skipping %s",
                intent.pair,
            )
            return

        oanda = await ExchangeConnectionsRepository().get_oanda()
        access_token = oanda.get("access_token") or ""
        account_id = oanda.get("account_id") or ""
        if not access_token.strip() or not account_id.strip():
            logger.warning("OANDA not configured — logging intent only for %s", intent.pair)
            await BrokerStateService().place_from_intent("oanda", intent)
            return

        intent_payload = asdict(intent)
        intent_payload["units"] = self._estimate_units(intent)
        intent_with_units = TradeIntent(**intent_payload)
        saved = await BrokerStateService().place_from_intent("oanda", intent_with_units)
        logger.info(
            "Forex associate placed order %s %s units=%s lot_id=%s broker_lot_id=%s",
            intent.pair,
            intent.direction,
            intent_payload["units"],
            saved.get("id"),
            saved.get("broker_lot_id"),
        )
