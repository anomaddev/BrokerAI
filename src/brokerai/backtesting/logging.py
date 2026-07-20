"""Buffered logging handler that flushes backtest log lines to Postgres."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from brokerai.db.repositories.backtest_logs import BacktestLogsRepository


class BufferedBacktestLogHandler(logging.Handler):
    """Buffer log records; flush only from the async worker path.

    Never schedules ``create_task`` from ``emit`` — that races with
    process-pool ``asyncio.run()`` teardown and can surface as
    ``Event loop is closed`` during candle backfill.
    """

    def __init__(
        self,
        run_id: str,
        *,
        verbose: bool = False,
        flush_interval_s: float = 0.75,
        flush_size: int = 40,
    ) -> None:
        super().__init__(level=logging.DEBUG if verbose else logging.INFO)
        self.run_id = run_id
        self.verbose = verbose
        self.flush_interval_s = flush_interval_s
        self.flush_size = flush_size
        self._buffer: list[dict[str, Any]] = []
        self._last_flush = time.monotonic()
        self._repo = BacktestLogsRepository()

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.DEBUG:
            return
        if not self.verbose and record.levelno < logging.INFO:
            return
        meta = getattr(record, "backtest_meta", None)
        self._buffer.append(
            {
                "level": record.levelname,
                "message": self.format(record) if self.formatter else record.getMessage(),
                "meta": dict(meta) if isinstance(meta, dict) else None,
                "created_at": datetime.now(timezone.utc),
            }
        )

    def should_flush(self) -> bool:
        if not self._buffer:
            return False
        if len(self._buffer) >= self.flush_size:
            return True
        return (time.monotonic() - self._last_flush) >= self.flush_interval_s

    async def flush_async(self) -> None:
        if not self._buffer:
            return
        batch = self._buffer
        self._buffer = []
        self._last_flush = time.monotonic()
        try:
            await self._repo.insert_many(self.run_id, batch)
        except Exception:
            # Never let logging crash the worker.
            pass

    def close(self) -> None:
        # Buffer is drained via flush_async before the event loop closes.
        super().close()


def attach_backtest_logger(
    run_id: str,
    *,
    verbose: bool = False,
) -> tuple[logging.Logger, BufferedBacktestLogHandler]:
    logger = logging.getLogger(f"brokerai.backtesting.run.{run_id}")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    handler = BufferedBacktestLogHandler(run_id, verbose=verbose)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger, handler
