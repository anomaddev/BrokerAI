import asyncio
import json
import logging
import signal
from datetime import datetime, timezone
from pathlib import Path

from brokerai.activity.constants import (
    ACTION_BOT_ERROR,
    ACTION_DAILY_REPORT_COMPLETED,
    ACTION_DAILY_REPORT_FAILED,
    ACTION_ORCHESTRATOR_STARTED,
    ACTION_ORCHESTRATOR_STOPPED,
    ACTION_WEEKLY_BRIEF_COMPLETED,
    ACTION_WEEKLY_DEBRIEF_COMPLETED,
)
from brokerai.activity.log import record_bot_activity
from brokerai.activity.monitor import ActivityMonitor
from brokerai.bots import get_bot_registry
from brokerai.bots.base import Bot
from brokerai.config.settings import get_settings, validate_startup_settings
from brokerai.core.control import ControlServer

logger = logging.getLogger(__name__)

_LEGACY_PIPELINE_BOTS = frozenset({"data_manager", "data_analyzer", "executor", "brokers"})


class Orchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.bots: dict[str, Bot] = {}
        self._running = False
        self._started_at: datetime | None = None
        self._tasks: dict[str, asyncio.Task] = {}

    def _resolved_bot_names(self, use_secretary: bool) -> list[str]:
        """Return bot names to load, auto-injecting Secretary pipeline bots when required."""
        names = list(self.settings.enabled_bot_names)
        if not use_secretary:
            return names

        for required in ("secretary", "broker"):
            if required not in names:
                names.append(required)
                logger.info(
                    "Auto-enabled '%s' — required when BROKERAI_USE_SECRETARY_PIPELINE=true",
                    required,
                )
        return names

    def _load_bots(self) -> None:
        bot_registry = get_bot_registry()
        use_secretary = self.settings.use_secretary_pipeline

        for name in self._resolved_bot_names(use_secretary):
            if use_secretary and name in _LEGACY_PIPELINE_BOTS:
                logger.info(
                    "Skipping legacy bot '%s' — use_secretary_pipeline is enabled",
                    name,
                )
                continue
            bot_cls = bot_registry.get(name)
            if bot_cls is None:
                logger.warning("Unknown bot '%s', skipping", name)
                continue
            self.bots[name] = bot_cls()

        self._wire_bots(use_secretary)

        if use_secretary:
            if "secretary" not in self.bots:
                logger.warning(
                    "use_secretary_pipeline is enabled but secretary is not in enabled_bots — "
                    "candle fetch and strategy analysis will not run"
                )
        else:
            has_manager = "data_manager" in self.bots
            has_analyzer = "data_analyzer" in self.bots
            if has_manager and not has_analyzer:
                logger.warning(
                    "data_manager is enabled without data_analyzer — candles will be cached "
                    "but strategy analysis will not run on new bars"
                )

    def _wire_bots(self, use_secretary: bool) -> None:
        secretary = self.bots.get("secretary")
        broker = self.bots.get("broker")

        if secretary is not None and broker is not None:
            if hasattr(secretary, "attach_broker"):
                secretary.attach_broker(broker)
            if hasattr(broker, "attach_data_manager") and hasattr(secretary, "service"):
                broker.attach_data_manager(secretary.service)

        if use_secretary:
            return

        data_analyzer = self.bots.get("data_analyzer")
        executor = self.bots.get("executor")
        brokers = self.bots.get("brokers")
        data_manager = self.bots.get("data_manager")
        if data_manager is not None and hasattr(data_manager, "service"):
            service = data_manager.service
            for bot in (data_analyzer, executor, brokers):
                if bot is not None and hasattr(bot, "attach_data_manager"):
                    bot.attach_data_manager(service)
        if (
            data_analyzer is not None
            and executor is not None
            and hasattr(executor, "attach_data_analyzer")
        ):
            executor.attach_data_analyzer(data_analyzer)
        if executor is not None and brokers is not None and hasattr(brokers, "attach_executor"):
            brokers.attach_executor(executor)

    def _tick_interval_seconds(self, name: str) -> float:
        settings = self.settings
        if name == "secretary":
            return float(settings.secretary_tick_interval_seconds)
        if name == "broker":
            return float(settings.broker_sync_interval_seconds)
        return 5.0

    async def _run_startup_pass(self) -> None:
        if self.settings.use_secretary_pipeline:
            return

        data_manager = self.bots.get("data_manager")
        data_analyzer = self.bots.get("data_analyzer")

        if data_manager is None and data_analyzer is None:
            return

        if data_manager is not None:
            logger.info("Orchestrator startup — warming candle cache")
            try:
                await data_manager.tick()
            except Exception:
                logger.exception("Orchestrator startup — data_manager pass failed")

        if data_analyzer is not None and hasattr(data_analyzer, "run_startup_pass"):
            try:
                await data_analyzer.run_startup_pass()
            except Exception:
                logger.exception("Orchestrator startup — data_analyzer pass failed")

        executor = self.bots.get("executor")
        if executor is not None and hasattr(executor, "run_startup_pass"):
            try:
                await executor.run_startup_pass()
            except Exception:
                logger.exception("Orchestrator startup — executor pass failed")

    async def start_all(self) -> None:
        for name, bot in self.bots.items():
            await bot.start()

        await self._run_startup_pass()

        for name, bot in self.bots.items():
            self._tasks[name] = asyncio.create_task(self._run_bot(name, bot))
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        logger.info("Orchestrator started %d bot(s)", len(self.bots))
        await record_bot_activity(
            ACTION_ORCHESTRATOR_STARTED,
            "Orchestrator started",
            detail=f"Running {len(self.bots)} module(s)",
            source="orchestrator",
            occurred_at=self._started_at,
        )

    async def stop_all(self) -> None:
        if self._running:
            await record_bot_activity(
                ACTION_ORCHESTRATOR_STOPPED,
                "Orchestrator stopped",
                source="orchestrator",
            )
        self._running = False
        self._started_at = None
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

    async def get_pipeline_status(self) -> dict:
        secretary = self.bots.get("secretary")
        if secretary is None:
            return {"enabled": False}
        status = await secretary.status()
        return {
            "enabled": True,
            "use_secretary_pipeline": self.settings.use_secretary_pipeline,
            "queued_jobs": status.get("queued_jobs", 0),
            "active_pipelines": status.get("active_pipelines", 0),
            "last_completed_at": status.get("last_completed_at"),
            "avg_pipeline_duration_ms": status.get("avg_pipeline_duration_ms"),
            "max_backlog_seen": status.get("max_backlog_seen"),
            "worker_pool": status.get("worker_pool"),
        }

    async def _run_bot(self, name: str, bot: Bot) -> None:
        interval = self._tick_interval_seconds(name)
        while self._running:
            try:
                await bot.tick()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Bot '%s' error: %s", name, exc)
                bot.mark_error(exc)
                await record_bot_activity(
                    ACTION_BOT_ERROR,
                    f"{name.replace('_', ' ').title()} error",
                    detail=str(exc),
                    source=name,
                    metadata={"bot": name},
                )
                await asyncio.sleep(interval)

    async def activity_monitor_loop(self, monitor: ActivityMonitor) -> None:
        while self._running:
            try:
                await monitor.tick()
            except Exception:
                logger.warning("Activity monitor tick failed", exc_info=True)
            await asyncio.sleep(60)

    async def heartbeat_loop(self) -> None:
        while self._running:
            data_dir = self.settings.data_dir
            data_dir.mkdir(parents=True, exist_ok=True)
            heartbeat = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "running": self._running,
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "bots": await self.get_statuses(),
                "pipeline": await self.get_pipeline_status(),
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
    validate_startup_settings()
    try:
        from brokerai.tasks.runner import reconcile_stale_active_task

        reconcile_stale_active_task()
    except Exception:
        logger.warning("Background task reconciliation failed", exc_info=True)
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
    activity_monitor = ActivityMonitor()
    activity_task = asyncio.create_task(orchestrator.activity_monitor_loop(activity_monitor))

    await stop_event.wait()
    heartbeat_task.cancel()
    control_task.cancel()
    activity_task.cancel()
    await asyncio.gather(heartbeat_task, control_task, activity_task, return_exceptions=True)
    await orchestrator.stop_all()
