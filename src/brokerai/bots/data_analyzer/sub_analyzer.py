from abc import ABC, abstractmethod


class SubAnalyzer(ABC):
    trade_id: str

    def __init__(self, trade_id: str) -> None:
        self.trade_id = trade_id

    @abstractmethod
    async def evaluate(self) -> None:
        """Evaluate exit signals for a monitored trade."""
