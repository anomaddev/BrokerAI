from __future__ import annotations

import logging
from dataclasses import asdict

from brokerai.bots.associate.assets.crypto import CryptoAssociate
from brokerai.bots.associate.assets.forex import ForexAssociate
from brokerai.bots.associate.assets.futures import FuturesAssociate
from brokerai.bots.associate.assets.metals import MetalsAssociate
from brokerai.bots.associate.assets.options import OptionsAssociate
from brokerai.bots.associate.assets.stocks import StocksAssociate
from brokerai.bots.base import EphemeralBot, WorkerResult
from brokerai.trading.types import TradeIntent

logger = logging.getLogger(__name__)

_ASSOCIATES = {
    "forex": ForexAssociate(),
    "crypto": CryptoAssociate(),
    "stocks": StocksAssociate(),
    "futures": FuturesAssociate(),
    "options": OptionsAssociate(),
    "metals": MetalsAssociate(),
}


class AssociateWorker(EphemeralBot[TradeIntent, dict]):
    """Spin-up worker that routes a trade intent to the asset-specific associate."""

    name = "associate_worker"

    def __init__(self) -> None:
        super().__init__()
        self.asset_class = "multi"

    async def run(self, request: TradeIntent) -> WorkerResult[dict]:
        associate = _ASSOCIATES.get(request.asset_class)
        if associate is None:
            return WorkerResult(
                ok=False,
                error=f"Unknown asset class: {request.asset_class}",
            )
        try:
            await associate.place_order(asdict(request))
            return WorkerResult(ok=True, data={"pair": request.pair, "direction": request.direction})
        except Exception as exc:
            logger.exception("Associate failed for %s", request.pair)
            return WorkerResult(ok=False, error=str(exc))
