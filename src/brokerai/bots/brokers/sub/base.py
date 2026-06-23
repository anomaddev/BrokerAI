from abc import ABC, abstractmethod


class SubBroker(ABC):
    asset_class: str = "base"

    @abstractmethod
    async def on_start(self) -> None:
        """Sub-broker startup hook."""

    @abstractmethod
    async def route(self, action: str, payload: dict | None = None) -> None:
        """Route an action for this asset class."""
