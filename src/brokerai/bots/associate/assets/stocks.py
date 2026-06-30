from __future__ import annotations

import logging

from brokerai.bots.associate.assets.base import AssetAssociate

logger = logging.getLogger(__name__)


class _StubAssociate(AssetAssociate):
    async def place_order(self, payload: dict) -> None:
        # TODO(loop): implement {self.asset_class} associate execution
        logger.info(
            "TODO(loop): implement %s associate — would place order %s",
            self.asset_class,
            payload.get("pair"),
        )


class CryptoAssociate(_StubAssociate):
    asset_class = "crypto"


class StocksAssociate(_StubAssociate):
    asset_class = "stocks"


class FuturesAssociate(_StubAssociate):
    asset_class = "futures"


class OptionsAssociate(_StubAssociate):
    asset_class = "options"


class MetalsAssociate(_StubAssociate):
    asset_class = "metals"
