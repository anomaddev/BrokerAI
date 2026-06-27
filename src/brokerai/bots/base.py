from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum


class BotState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


class Bot(ABC):
    name: str = "base"

    def __init__(self) -> None:
        self._state = BotState.STOPPED
        self._last_error: str | None = None
        self._started_at: datetime | None = None

    async def start(self) -> None:
        self._state = BotState.RUNNING
        self._started_at = datetime.now(timezone.utc)
        self._last_error = None
        await self.on_start()

    async def stop(self) -> None:
        await self.on_stop()
        self._state = BotState.STOPPED
        self._started_at = None

    async def status(self) -> dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_error": self._last_error,
        }

    def mark_error(self, error: str | Exception) -> None:
        self._state = BotState.ERROR
        self._last_error = str(error)

    @abstractmethod
    async def on_start(self) -> None:
        """Sub-bot startup hook."""

    @abstractmethod
    async def on_stop(self) -> None:
        """Sub-bot shutdown hook."""

    @abstractmethod
    async def tick(self) -> None:
        """Periodic work loop iteration."""
