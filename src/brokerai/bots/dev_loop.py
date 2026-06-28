"""Run a single bot on a tick loop outside the orchestrator (for local development)."""

from __future__ import annotations

import asyncio
import logging
import signal

from brokerai.bots import BOT_REGISTRY

logger = logging.getLogger(__name__)


async def run_bot_loop(
    bot_name: str,
    *,
    interval_seconds: float = 5.0,
    once: bool = False,
) -> None:
    """Start *bot_name*, call ``tick()`` on an interval until interrupted."""
    bot_cls = BOT_REGISTRY.get(bot_name)
    if bot_cls is None:
        known = ", ".join(sorted(BOT_REGISTRY))
        raise ValueError(f"Unknown bot {bot_name!r}. Known: {known}")

    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")

    bot = bot_cls()
    stop_event = asyncio.Event()

    def _handle_signal(*_: object) -> None:
        logger.info("Stopping %s dev loop", bot_name)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    try:
        from brokerai.db.indexes import ensure_indexes

        await ensure_indexes()
    except Exception:
        logger.warning("MongoDB unavailable — indexes not ensured", exc_info=True)

    await bot.start()
    tick = 0
    try:
        while not stop_event.is_set():
            tick += 1
            try:
                logger.info("%s tick #%d", bot_name, tick)
                await bot.tick()
            except Exception:
                logger.exception("%s tick #%d failed", bot_name, tick)
            if once:
                break
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                break
            except TimeoutError:
                pass
    finally:
        await bot.stop()
