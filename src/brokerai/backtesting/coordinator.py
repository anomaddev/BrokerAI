"""API-process coordinator that claims queued backtests into a process pool."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import Any
from uuid import uuid4

from brokerai.backtesting.worker import run_backtest_job, run_backtest_job_async
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUS_COMPLETED,
    BACKTEST_RUN_STATUS_RUNNING,
    BacktestRunsRepository,
)
from brokerai.db.repositories.backtest_settings import BacktestSettingsRepository
from brokerai.db.repositories.strategies import (
    BACKTEST_STATUS_RUNNING,
    StrategiesRepository,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 1.0
POOL_JOIN_TIMEOUT_S = 5.0


class BacktestCoordinator:
    """Claim queued runs and execute them with a capped process pool."""

    def __init__(self, *, use_processes: bool = True) -> None:
        self._use_processes = use_processes
        self._pool: ProcessPoolExecutor | None = None
        self._pool_size = 0
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        # Tracks runs submitted via manual start when auto_start is false.
        self._manual_ready: set[str] = set()

    @property
    def is_started(self) -> bool:
        """True when the claim loop is running in *this* process."""
        return self._task is not None and not self._task.done()

    def notify_manual_start(self, run_id: str) -> None:
        self._manual_ready.add(run_id)

    @staticmethod
    def _close_pool_sync(
        pool: ProcessPoolExecutor,
        *,
        wait: bool,
        cancel_futures: bool,
        join_timeout_s: float = POOL_JOIN_TIMEOUT_S,
    ) -> None:
        """Shut down a pool and ensure worker processes fully exit.

        ``ProcessPoolExecutor.shutdown(wait=False)`` alone leaves spawn workers
        (and their semaphores) alive — that is the usual cause of the
        ``resource_tracker: ... leaked semaphore objects`` warning on Ctrl+C /
        uvicorn reload.
        """
        # Snapshot before shutdown; the executor may clear ``_processes``.
        processes = list((getattr(pool, "_processes", None) or {}).values())
        try:
            pool.shutdown(wait=wait, cancel_futures=cancel_futures)
        except Exception:
            logger.warning("Process pool shutdown failed", exc_info=True)

        if not processes:
            return

        if wait:
            # shutdown(wait=True) should have joined; still reap stragglers.
            for proc in processes:
                try:
                    proc.join(timeout=0.1)
                except Exception:
                    pass
            return

        for proc in processes:
            try:
                if proc.is_alive():
                    proc.terminate()
            except Exception:
                pass
        for proc in processes:
            try:
                proc.join(timeout=join_timeout_s)
                if proc.is_alive():
                    proc.kill()
                    proc.join(timeout=1.0)
            except Exception:
                pass

    def _ensure_pool(self, size: int) -> ProcessPoolExecutor | None:
        if not self._use_processes:
            return None
        size = max(1, min(10, size))
        if self._pool is not None and self._pool_size == size:
            return self._pool
        # Never abandon an in-use pool: concurrency is already capped by
        # ``slots`` / ``_inflight``. Resize only when idle so workers join
        # cleanly and spawn semaphores are released.
        if self._pool is not None and self._inflight:
            return self._pool
        if self._pool is not None:
            old = self._pool
            self._pool = None
            self._pool_size = 0
            self._close_pool_sync(old, wait=True, cancel_futures=False)
        ctx = multiprocessing.get_context("spawn")
        # One job per child avoids asyncio/httpx/SQLAlchemy globals bound to a
        # closed event loop when the interpreter is reused across asyncio.run().
        self._pool = ProcessPoolExecutor(
            max_workers=size,
            mp_context=ctx,
            max_tasks_per_child=1,
        )
        self._pool_size = size
        logger.info("Backtest process pool sized to %d workers (max_tasks_per_child=1)", size)
        return self._pool

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        # Resume orphaned running runs after API restart.
        try:
            for run_id in await BacktestRunsRepository().list_claimable_manual_starts():
                self._manual_ready.add(run_id)
        except Exception:
            logger.warning("Failed to resume orphaned backtest runs", exc_info=True)
        self._task = asyncio.create_task(self._loop(), name="backtest-coordinator")
        logger.info("Backtest coordinator started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        inflight_ids = list(self._inflight)
        for fut in list(self._inflight.values()):
            fut.cancel()
        self._inflight.clear()
        self._manual_ready.clear()
        # Drop leases so a reloaded API process can reclaim without waiting for
        # stale-heartbeat timeout — superseded workers exit on the next check.
        if inflight_ids:
            runs_repo = BacktestRunsRepository()
            for rid in inflight_ids:
                try:
                    await runs_repo.clear_worker_claim(rid)
                except Exception:
                    logger.warning(
                        "Failed to clear worker claim for %s on coordinator stop",
                        rid,
                        exc_info=True,
                    )
        pool = self._pool
        self._pool = None
        self._pool_size = 0
        if pool is not None:
            # Don't block forever on mid-flight backtests during Ctrl+C / reload;
            # terminate workers so multiprocessing semaphores are released.
            await asyncio.to_thread(
                self._close_pool_sync,
                pool,
                wait=False,
                cancel_futures=True,
            )
        logger.info("Backtest coordinator stopped")

    async def _reclaim_orphaned_runs(self, runs_repo: BacktestRunsRepository) -> None:
        """Pick up running runs that were marked outside this process.

        Startup drain can run in the orchestrator/secretary process, which may
        call ``mark_running`` + ``notify_manual_start`` on a coordinator that was
        never ``start()``-ed. The API coordinator must reclaim those orphans.
        Also finish cancel-requested runs that never got a worker.
        """
        try:
            cancelled = await runs_repo.finish_orphaned_cancel_requests()
            for rid in cancelled:
                self._manual_ready.discard(rid)
                logger.info("Finished orphaned cancel-requested backtest %s", rid)
            for rid in await runs_repo.list_claimable_manual_starts():
                if rid not in self._inflight:
                    self._manual_ready.add(rid)
        except Exception:
            logger.warning("Failed to reclaim orphaned backtest runs", exc_info=True)

    async def _loop(self) -> None:
        runs_repo = BacktestRunsRepository()
        settings_repo = BacktestSettingsRepository()
        strategies_repo = StrategiesRepository()
        while not self._stop.is_set():
            try:
                # Reap finished futures.
                done_ids = [rid for rid, fut in self._inflight.items() if fut.done()]
                for rid in done_ids:
                    fut = self._inflight.pop(rid)
                    result: Any = None
                    try:
                        result = fut.result()
                    except Exception:
                        logger.exception("Backtest future failed for run %s", rid)
                        continue
                    status = None
                    if isinstance(result, dict):
                        status = result.get("status")
                        if not status and isinstance(result.get("run"), dict):
                            status = result["run"].get("status")
                    if status == BACKTEST_RUN_STATUS_COMPLETED:
                        try:
                            from brokerai.backtesting.ai_feedback import (
                                maybe_auto_analyze_backtest,
                            )

                            asyncio.create_task(
                                maybe_auto_analyze_backtest(rid),
                                name=f"backtest-ai-auto-{rid}",
                            )
                        except Exception:
                            logger.warning(
                                "Failed to schedule auto AI feedback for %s",
                                rid,
                                exc_info=True,
                            )

                await self._reclaim_orphaned_runs(runs_repo)

                settings = await settings_repo.get()
                max_concurrent = int(settings["max_concurrent"])
                auto_start = bool(settings["auto_start"])
                slots = max(0, max_concurrent - len(self._inflight))

                while slots > 0:
                    run: dict[str, Any] | None = None
                    # Prefer resuming already-running jobs (manual start or orphan recovery).
                    for rid in list(self._manual_ready):
                        if rid in self._inflight:
                            continue
                        doc = await runs_repo.get_by_id(rid)
                        if doc and doc.get("status") == BACKTEST_RUN_STATUS_RUNNING:
                            if doc.get("cancel_requested"):
                                self._manual_ready.discard(rid)
                                continue
                            run = doc
                            self._manual_ready.discard(rid)
                            break
                        self._manual_ready.discard(rid)

                    if run is None and auto_start:
                        run = await runs_repo.claim_next_queued()

                    if run is None:
                        break

                    run_id = str(run["id"])
                    if run_id in self._inflight:
                        continue
                    worker_token = uuid4().hex
                    claimed = await runs_repo.claim_for_worker(run_id, worker_token)
                    if claimed is None:
                        logger.info(
                            "Skip backtest %s — another worker already holds the lease",
                            run_id,
                        )
                        # Avoid spinning on the same contested run within this tick.
                        if run is not None and not auto_start:
                            break
                        continue
                    strategy_id = str(run.get("strategy_id") or "")
                    if strategy_id:
                        await strategies_repo.set_backtest_status(
                            strategy_id, BACKTEST_STATUS_RUNNING
                        )
                    self._submit(run_id, worker_token, max_concurrent)
                    slots -= 1

            except Exception:
                logger.exception("Backtest coordinator tick failed")

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=POLL_INTERVAL_S)
            except asyncio.TimeoutError:
                pass

    def _submit(self, run_id: str, worker_token: str, pool_size: int) -> None:
        if run_id in self._inflight:
            return
        loop = asyncio.get_running_loop()
        if self._use_processes:
            pool = self._ensure_pool(pool_size)
            assert pool is not None
            fut = loop.run_in_executor(pool, run_backtest_job, run_id, worker_token)
        else:
            fut = loop.create_task(run_backtest_job_async(run_id, worker_token))
        self._inflight[run_id] = fut  # type: ignore[assignment]
        logger.info("Submitted backtest run %s (inflight=%d)", run_id, len(self._inflight))


_coordinator: BacktestCoordinator | None = None


def get_backtest_coordinator() -> BacktestCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = BacktestCoordinator(use_processes=True)
    return _coordinator
