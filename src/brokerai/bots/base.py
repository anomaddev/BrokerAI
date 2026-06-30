from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar

RequestT = TypeVar("RequestT")
ResultT = TypeVar("ResultT")


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


@dataclass
class WorkerResult(Generic[ResultT]):
    """Output from a one-shot ephemeral worker run."""

    ok: bool
    data: ResultT | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class EphemeralBot(Bot, Generic[RequestT, ResultT]):
    """Spin-up/spin-down worker invoked by Secretary or Broker via WorkerPool."""

    async def on_start(self) -> None:
        return None

    async def on_stop(self) -> None:
        return None

    async def tick(self) -> None:
        """No-op — ephemeral workers are invoked via run()."""

    @abstractmethod
    async def run(self, request: RequestT) -> WorkerResult[ResultT]:
        """Execute one unit of work and return a structured result."""
