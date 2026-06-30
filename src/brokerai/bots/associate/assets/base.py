from abc import ABC, abstractmethod


class AssetAssociate(ABC):
    asset_class: str = "base"

    @abstractmethod
    async def place_order(self, payload: dict) -> None:
        """Execute a trade for this asset class."""
