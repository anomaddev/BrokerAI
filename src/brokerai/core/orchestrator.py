import asyncio
import json
import logging
import signal
from datetime import datetime, timezone
from pathlib import Path

from brokerai.bots import BOT_REGISTRY, Bot
from brokerai.bots.base import BotState
from brokerai.config.settings import get_settings
from brokerai.core.control import ControlServer

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.bots: dict[str, Bot] = {}
        self._running = False
        self._tasks: dict[str, asyncio.Task] = {}

    def _load_bots(self) -> None:
        for name in self.settings.enabled_bot_names:
            bot_cls = BOT_REGISTRY.get(name)
            if bot_cls is None:
                logger.warning("Unknown bot '%s', skipping", name)
                continue
            self.bots[name] = bot_cls()

    async def start_all(self) -> None:
        for name, bot in self.bots.items():
            await bot.start()
            self._tasks[name] = asyncio.create_task(self._run_bot(name, bot))
        self._running = True
        logger.info("Orchestrator started %d bot(s)", len(self.bots))

    async def stop_all(self) -> None:
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        for bot in self.bots.values():
            await bot.stop()
        logger.info("Orchestrator stopped all bots")

    async def start_bot(self, name: str) -> bool:
        bot = self.bots.get(name)
        if bot is None:
            return False
        if name in self._tasks and not self._tasks[name].done():
            return True
        await bot.start()
        self._tasks[name] = asyncio.create_task(self._run_bot(name, bot))
        return True

    async def stop_bot(self, name: str) -> bool:
        bot = self.bots.get(name)
        if bot is None:
            return False
        task = self._tasks.pop(name, None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await bot.stop()
        return True

    async def get_statuses(self) -> list[dict]:
        return [await bot.status() for bot in self.bots.values()]

    async def _run_bot(self, name: str, bot: Bot) -> None:
        while self._running:
            try:
                await bot.tick()
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Bot '%s' error: %s", name, exc)
                bot._state = BotState.ERROR  # noqa: SLF001
                bot._last_error = str(exc)  # noqa: SLF001
                await asyncio.sleep(5)

    async def heartbeat_loop(self) -> None:
        while self._running:
            data_dir = self.settings.data_dir
            data_dir.mkdir(parents=True, exist_ok=True)
            heartbeat = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "running": self._running,
                "bots": await self.get_statuses(),
            }
            (data_dir / "heartbeat.json").write_text(json.dumps(heartbeat, indent=2))
            await asyncio.sleep(10)

    async def control_loop(self) -> None:
        server = ControlServer(self, self.settings)
        server.ensure()
        while self._running:
            await server.process_pending()
            await asyncio.sleep(0.5)


_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
        _orchestrator._load_bots()
    return _orchestrator


async def run_orchestrator() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    orchestrator = get_orchestrator()
    stop_event = asyncio.Event()

    def _handle_signal(*_: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    await orchestrator.start_all()

    try:
        from brokerai.db.indexes import ensure_indexes

        await ensure_indexes()
    except Exception:
        logger.warning("MongoDB unavailable — indexes not ensured", exc_info=True)

    heartbeat_task = asyncio.create_task(orchestrator.heartbeat_loop())
    control_task = asyncio.create_task(orchestrator.control_loop())

    await stop_event.wait()
    heartbeat_task.cancel()
    control_task.cancel()
    await asyncio.gather(heartbeat_task, control_task, return_exceptions=True)
    await orchestrator.stop_all()
