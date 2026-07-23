"""File-based IPC for orchestrator control commands."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from brokerai.config.settings import Settings, get_settings

if TYPE_CHECKING:
    from brokerai.core.orchestrator import Orchestrator

ControlAction = Literal["start", "stop", "restart", "status"]


@dataclass
class ControlCommand:
    id: str
    action: ControlAction
    bot: str
    timestamp: str

    @classmethod
    def create(cls, action: ControlAction, bot: str) -> ControlCommand:
        return cls(
            id=str(uuid.uuid4()),
            action=action,
            bot=bot,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlCommand:
        return cls(
            id=str(data["id"]),
            action=data["action"],
            bot=str(data["bot"]),
            timestamp=str(data["timestamp"]),
        )


@dataclass
class ControlResult:
    id: str
    ok: bool
    action: ControlAction
    bot: str
    message: str
    timestamp: str
    bot_status: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ControlPaths:
    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.root = settings.data_dir / "control"
        self.inbox = self.root / "inbox"
        self.outbox = self.root / "outbox"

    def ensure(self) -> None:
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.outbox.mkdir(parents=True, exist_ok=True)


class ControlError(Exception):
    pass


class ControlTimeout(ControlError):
    pass


class ControlClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.paths = ControlPaths(settings)

    def submit(
        self,
        action: ControlAction,
        bot: str,
        *,
        timeout: float = 5.0,
        poll_interval: float = 0.2,
    ) -> ControlResult:
        self.paths.ensure()
        command = ControlCommand.create(action, bot)
        inbox_path = self.paths.inbox / f"{command.id}.json"
        outbox_path = self.paths.outbox / f"{command.id}.json"
        inbox_path.write_text(json.dumps(command.to_dict(), indent=2))

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if outbox_path.exists():
                data = json.loads(outbox_path.read_text())
                outbox_path.unlink(missing_ok=True)
                return ControlResult(
                    id=data["id"],
                    ok=bool(data["ok"]),
                    action=data["action"],
                    bot=data["bot"],
                    message=str(data["message"]),
                    timestamp=str(data["timestamp"]),
                    bot_status=data.get("bot_status"),
                )
            time.sleep(poll_interval)

        inbox_path.unlink(missing_ok=True)
        raise ControlTimeout(
            f"Orchestrator did not respond within {timeout}s — is it running?"
        )


class ControlServer:
    def __init__(self, orchestrator: Orchestrator, settings: Settings | None = None) -> None:
        self.orchestrator = orchestrator
        self.paths = ControlPaths(settings)

    def ensure(self) -> None:
        self.paths.ensure()

    async def process_pending(self) -> None:
        self.ensure()
        for path in sorted(self.paths.inbox.glob("*.json")):
            try:
                command = ControlCommand.from_dict(json.loads(path.read_text()))
                result = await self._handle(command)
            except Exception as exc:  # noqa: BLE001
                result = ControlResult(
                    id=path.stem,
                    ok=False,
                    action="status",
                    bot="",
                    message=str(exc),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            outbox_path = self.paths.outbox / f"{result.id}.json"
            outbox_path.write_text(json.dumps(result.to_dict(), indent=2))
            path.unlink(missing_ok=True)

    async def _handle(self, command: ControlCommand) -> ControlResult:
        bot = command.bot
        if command.action == "status":
            statuses = await self.orchestrator.get_statuses()
            match = next((s for s in statuses if s["name"] == bot), None)
            if match is None:
                return ControlResult(
                    id=command.id,
                    ok=False,
                    action=command.action,
                    bot=bot,
                    message=f"Bot '{bot}' not found",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            return ControlResult(
                id=command.id,
                ok=True,
                action=command.action,
                bot=bot,
                message="ok",
                timestamp=datetime.now(timezone.utc).isoformat(),
                bot_status=match,
            )

        # Reserved control target: restart every module without killing control loops.
        if command.action == "restart" and bot == "orchestrator":
            ok = await self.orchestrator.restart_all_bots()
            return ControlResult(
                id=command.id,
                ok=ok,
                action=command.action,
                bot=bot,
                message=(
                    "Orchestrator modules restarted"
                    if ok
                    else "Failed to restart orchestrator modules (is it running?)"
                ),
                timestamp=datetime.now(timezone.utc).isoformat(),
                bot_status={"running": bool(getattr(self.orchestrator, "_running", False))},
            )

        if bot not in self.orchestrator.bots:
            return ControlResult(
                id=command.id,
                ok=False,
                action=command.action,
                bot=bot,
                message=f"Bot '{bot}' not found",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        if command.action == "start":
            ok = await self.orchestrator.start_bot(bot)
        elif command.action == "restart":
            ok = await self.orchestrator.restart_bot(bot)
        elif command.action == "stop":
            ok = await self.orchestrator.stop_bot(bot)
        else:
            return ControlResult(
                id=command.id,
                ok=False,
                action=command.action,
                bot=bot,
                message=f"Unsupported action '{command.action}'",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        status = await self.orchestrator.bots[bot].status()
        return ControlResult(
            id=command.id,
            ok=ok,
            action=command.action,
            bot=bot,
            message=f"Bot '{bot}' {command.action} accepted" if ok else f"Failed to {command.action} '{bot}'",
            timestamp=datetime.now(timezone.utc).isoformat(),
            bot_status=status,
        )
