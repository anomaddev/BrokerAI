"""Process-pool worker entrypoint for a single backtest run."""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

from brokerai.backtesting.engine import LostWorkerClaim, run_backtest_engine
from brokerai.backtesting.logging import attach_backtest_logger
from brokerai.db.pg.client import close_pg, init_pg, reset_pg_runtime_for_new_loop, session_scope
from brokerai.db.pg.models import BacktestRunRow
from brokerai.db.repositories.backtest_actions import BacktestActionsRepository
from brokerai.db.repositories.backtest_logs import BacktestLogsRepository
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUS_CANCELLED,
    BACKTEST_RUN_STATUS_COMPLETED,
    BACKTEST_RUN_STATUS_FAILED,
    BacktestRunsRepository,
    _sync_row_columns,
)
from brokerai.db.repositories.strategies import (
    BACKTEST_STATUS_CANCELLED,
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    StrategiesRepository,
)
from brokerai.integrations.oanda_client import close_oanda_client, reset_oanda_runtime_for_new_loop

logger = logging.getLogger(__name__)


def _reset_worker_runtime() -> None:
    """Clear loop-bound globals before a new ``asyncio.run()`` in a pool worker."""
    reset_pg_runtime_for_new_loop()
    reset_oanda_runtime_for_new_loop()


async def _set_strategy_status(strategy_id: str, status: str) -> None:
    if not strategy_id:
        return
    try:
        await StrategiesRepository().set_backtest_status(strategy_id, status)
    except Exception:
        logger.exception("Failed to update strategy backtest_status for %s", strategy_id)


async def _execute(run_id: str, worker_token: str = "") -> dict[str, Any]:
    await init_pg()
    runs_repo = BacktestRunsRepository()
    claim = (worker_token or "").strip()
    if claim:
        if not await runs_repo.worker_owns(run_id, claim):
            logger.warning("Backtest %s refused: worker claim %s not held", run_id, claim[:8])
            return {"ok": False, "error": "lost worker claim"}
        # Restart-safe: drop any partial rows from a previous overlapping worker.
        await BacktestActionsRepository().delete_for_run(run_id)
        await BacktestLogsRepository().delete_for_run(run_id)

    run_doc = await runs_repo.get_raw_doc(run_id)
    if run_doc is None:
        return {"ok": False, "error": "run not found"}

    verbose = bool(run_doc.get("verbose"))
    log, handler = attach_backtest_logger(run_id, verbose=verbose)
    strategy_id = str(run_doc.get("strategy_id") or "")

    async def cancel_check() -> bool:
        if handler.should_flush():
            await handler.flush_async()
        if claim and not await runs_repo.worker_owns(run_id, claim):
            raise LostWorkerClaim(f"lost worker claim for backtest {run_id}")
        return await runs_repo.is_cancel_requested(run_id)

    try:
        result = await run_backtest_engine(
            run_doc,
            log=log,
            cancel_check=cancel_check,
            worker_token=claim or None,
        )
        await handler.flush_async()
        status = str(result.get("status") or BACKTEST_RUN_STATUS_COMPLETED)
        finished = await runs_repo.finish_run(
            run_id,
            status=status,
            stats=result.get("stats"),
            equity_curve=result.get("equity_curve"),
            status_message=result.get("status_message"),
        )
        if result.get("period_start") or result.get("period_end"):
            raw = await runs_repo.get_raw_doc(run_id)
            if raw is not None:
                if result.get("period_start"):
                    raw["period_start"] = result["period_start"]
                if result.get("period_end"):
                    raw["period_end"] = result["period_end"]
                async with session_scope() as session:
                    row = await session.get(BacktestRunRow, run_id)
                    if row is not None:
                        _sync_row_columns(row, raw)

        if status == BACKTEST_RUN_STATUS_COMPLETED:
            await _set_strategy_status(strategy_id, BACKTEST_STATUS_COMPLETED)
        elif status == BACKTEST_RUN_STATUS_CANCELLED:
            await _set_strategy_status(strategy_id, BACKTEST_STATUS_CANCELLED)
        else:
            await _set_strategy_status(strategy_id, BACKTEST_STATUS_FAILED)
        return {"ok": True, "status": status, "run": finished}
    except LostWorkerClaim:
        try:
            await handler.flush_async()
        except Exception:
            pass
        log.warning("Backtest %s exiting — worker claim lost (another worker owns it)", run_id)
        # Do not finish_run: the active lease holder owns terminal status.
        return {"ok": False, "error": "lost worker claim"}
    except Exception as exc:
        try:
            await handler.flush_async()
        except Exception:
            pass
        tb = traceback.format_exc()
        log.error("Backtest failed: %s", exc)
        try:
            await handler.flush_async()
        except Exception:
            pass
        if claim and not await runs_repo.worker_owns(run_id, claim):
            return {"ok": False, "error": "lost worker claim"}
        await runs_repo.finish_run(
            run_id,
            status=BACKTEST_RUN_STATUS_FAILED,
            error=f"{exc}\n{tb}",
            status_message="Failed",
        )
        await _set_strategy_status(strategy_id, BACKTEST_STATUS_FAILED)
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            await handler.flush_async()
        except Exception:
            pass
        try:
            await close_oanda_client()
        except Exception:
            logger.debug("OANDA client cleanup failed in backtest worker", exc_info=True)
        try:
            await close_pg()
        except Exception:
            logger.debug("Postgres cleanup failed in backtest worker", exc_info=True)
            reset_pg_runtime_for_new_loop()


def run_backtest_job(run_id: str, worker_token: str = "") -> dict[str, Any]:
    """Picklable process-pool entrypoint. Receives only ``run_id`` (+ lease token)."""
    _reset_worker_runtime()
    try:
        return asyncio.run(_execute(run_id, worker_token))
    finally:
        # Ensure the next pooled job never sees loop-bound leftovers.
        _reset_worker_runtime()


async def run_backtest_job_async(run_id: str, worker_token: str = "") -> dict[str, Any]:
    """In-process async entrypoint (tests / fallback without a process pool)."""
    return await _execute(run_id, worker_token)
