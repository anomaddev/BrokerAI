from __future__ import annotations

from typing import Any, Protocol

from brokerai.trading.broker.models import (
    BrokerEvent,
    ExposureMismatch,
    PositionLot,
    SyncEventsResult,
)
from brokerai.trading.types import TradeIntent


class BrokerAdapter(Protocol):
    exchange_id: str

    async def sync_lots(
        self,
        credentials: dict[str, Any],
        account_id: str,
        *,
        state: str | None = None,
    ) -> tuple[list[PositionLot], str | None]: ...

    async def sync_events(
        self,
        credentials: dict[str, Any],
        account_id: str,
        *,
        since_cursor: str | None,
        full: bool = False,
    ) -> SyncEventsResult: ...

    async def validate_exposure(
        self,
        credentials: dict[str, Any],
        account_id: str,
        lots: list[PositionLot],
    ) -> list[ExposureMismatch]: ...

    async def place_from_intent(
        self,
        credentials: dict[str, Any],
        account_id: str,
        intent: TradeIntent,
    ) -> tuple[PositionLot, dict[str, Any]]: ...

    async def close_lot(
        self,
        credentials: dict[str, Any],
        account_id: str,
        broker_lot_id: str,
    ) -> tuple[PositionLot, dict[str, Any]]: ...

    async def fetch_open_lots_with_prices(
        self,
        credentials: dict[str, Any],
        account_id: str,
    ) -> list[PositionLot]: ...


_ADAPTERS: dict[str, BrokerAdapter] = {}


def register_adapter(adapter: BrokerAdapter) -> None:
    _ADAPTERS[adapter.exchange_id] = adapter


def get_adapter(exchange_id: str) -> BrokerAdapter:
    adapter = _ADAPTERS.get(exchange_id)
    if adapter is None:
        raise ValueError(f"No broker adapter registered for exchange: {exchange_id}")
    return adapter
