"""In-process backtest runner with optional step-through debugging.

Use this module to run a backtest from Python or the ``brokerai backtest`` CLI
and pause on selected bar events (signals, entries, exits, every bar, …).

Typical Python usage::

    from brokerai.backtesting.debug import run_backtest

    result = await run_backtest(
        strategy_id="…",
        instrument="EUR/USD",
        period="1m",
        interactive=True,
        break_on=("signal", "entry", "exit"),
    )

Or attach a custom hook::

    async def on_bar(snap):
        print(snap.bar_time, snap.analysis_signal, snap.gate_passed)

    result = await run_backtest(strategy_id="…", on_bar=on_bar)

Edge cases
----------
- Quiet bars (no signal / no trade) are skipped unless ``bar`` is in
  ``break_on``.
- ``until`` delays the first pause until that bar open-time (ISO / OANDA).
- Interactive mode reads stdin; EOF continues the run without further pauses.
- Cancelling from the REPL (`q`) finishes the run as ``cancelled``.
"""

from __future__ import annotations

import inspect
import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Sequence, TextIO

from brokerai.backtesting.engine import run_backtest_engine
from brokerai.backtesting.logging import attach_backtest_logger
from brokerai.backtesting.periods import resolve_period_window
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_PERIODS,
    BACKTEST_RUN_STATUS_CANCELLED,
    BACKTEST_RUN_STATUS_COMPLETED,
    BACKTEST_RUN_STATUS_FAILED,
    BacktestRunsRepository,
    normalize_backtest_period,
)
from brokerai.db.repositories.strategies import (
    BACKTEST_STATUS_CANCELLED,
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    StrategiesRepository,
)
from brokerai.trading.types import AnalysisResult

logger = logging.getLogger(__name__)

BREAK_KINDS = frozenset(
    {
        "bar",
        "action",
        "signal",
        "entry",
        "exit",
        "filter_fail",
    }
)

OnBarHook = Callable[["BacktestBarSnapshot"], Awaitable["StepAction | None"] | "StepAction | None"]


class StepAction(str, Enum):
    """Decision returned from an ``on_bar`` hook."""

    CONTINUE = "continue"
    CANCEL = "cancel"


@dataclass(frozen=True)
class BacktestBarSnapshot:
    """Engine state captured after one evaluation bar is fully processed.

    ``actions`` are the action rows emitted on this bar only (not yet flushed
    when the hook runs — they are still in the engine buffer). Quiet bars have
    an empty ``actions`` list.
    """

    bar_index: int
    period_start_idx: int
    bars_done: int
    total_bars: int
    bar_time: str
    candle: dict[str, Any]
    analysis: AnalysisResult
    gate_passed: bool
    gate_reasons: list[str]
    gate_details: dict[str, Any]
    closed_trade: dict[str, Any] | None
    position: dict[str, Any] | None
    actions: list[dict[str, Any]]
    equity: float
    closed_trade_count: int

    @property
    def analysis_signal(self) -> Any:
        return (self.analysis.metadata or {}).get("signal")

    @property
    def action_kinds(self) -> tuple[str, ...]:
        return tuple(str(a.get("kind") or "") for a in self.actions)

    def matches_break(self, break_on: Sequence[str]) -> bool:
        """Return True when this snapshot should pause for *break_on* kinds.

        ``exit`` also matches stop-loss / take-profit action kinds (``sl``,
        ``tp``) because those are exit events in the action stream.
        """
        kinds = {k.strip().lower() for k in break_on if k and str(k).strip()}
        if not kinds:
            return False
        if "bar" in kinds:
            return True
        if "action" in kinds and self.actions:
            return True
        action_kinds = set(self.action_kinds)
        for kind in ("signal", "entry", "filter_fail"):
            if kind in kinds and kind in action_kinds:
                return True
        if "exit" in kinds and action_kinds.intersection({"exit", "sl", "tp"}):
            return True
        return False

    def summary_line(self) -> str:
        """One-line human summary for REPL / logs."""
        parts = [
            f"bar {self.bars_done}/{self.total_bars}",
            self.bar_time or "?",
            f"o={self.candle.get('open')} h={self.candle.get('high')} "
            f"l={self.candle.get('low')} c={self.candle.get('close')}",
        ]
        signal = self.analysis_signal
        if signal and signal != "none":
            parts.append(f"signal={signal}")
        if self.analysis.direction:
            parts.append(
                f"dir={self.analysis.direction} "
                f"conf={self.analysis.confidence:.2f} "
                f"gate={'pass' if self.gate_passed else 'fail'}"
            )
        if self.actions:
            parts.append("actions=" + ",".join(self.action_kinds))
        if self.position:
            parts.append(
                f"pos={self.position.get('direction')}@{self.position.get('entry_price')}"
            )
        parts.append(f"equity={self.equity:.2f}")
        parts.append(f"trades={self.closed_trade_count}")
        return " | ".join(parts)


def serialize_position(position: Any) -> dict[str, Any] | None:
    """Serialize a ``SimulatedPosition`` (or None) for snapshots / JSON."""
    if position is None:
        return None
    return {
        "id": getattr(position, "id", None),
        "strategy_id": getattr(position, "strategy_id", None),
        "pair": getattr(position, "pair", None),
        "direction": getattr(position, "direction", None),
        "entry_price": getattr(position, "entry_price", None),
        "units": getattr(position, "units", None),
        "entry_time": getattr(position, "entry_time", None),
        "stop_loss": getattr(position, "stop_loss", None),
        "take_profit": getattr(position, "take_profit", None),
        "status": getattr(position, "status", None),
    }


def parse_break_on(raw: str | Sequence[str] | None) -> tuple[str, ...]:
    """Normalize CLI / API break-on specs into a sorted unique tuple.

    Accepts comma-separated strings or sequences. Unknown kinds raise
    ``ValueError``. Empty / None defaults to ``("action",)``.
    """
    if raw is None:
        return ("action",)
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    else:
        parts = [str(p).strip().lower() for p in raw if str(p).strip()]
    if not parts:
        return ("action",)
    unknown = sorted({p for p in parts if p not in BREAK_KINDS})
    if unknown:
        raise ValueError(
            f"Unknown break-on kind(s): {', '.join(unknown)}. "
            f"Valid: {', '.join(sorted(BREAK_KINDS))}"
        )
    # Preserve order while uniquifying.
    seen: list[str] = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return tuple(seen)


@dataclass
class InteractiveBacktestDebugger:
    """stdin REPL that pauses when ``BacktestBarSnapshot.matches_break`` is true.

    Commands
    --------
    ``n`` / ``next`` / empty
        Continue until the next matching break.
    ``c`` / ``continue``
        Disable further pauses and run to completion.
    ``bar`` / ``pos`` / ``analysis`` / ``gates`` / ``actions`` / ``equity``
        Inspect the current snapshot.
    ``pdb``
        Drop into :mod:`pdb` with ``snap`` bound locally.
    ``q`` / ``quit``
        Cancel the backtest.
    ``h`` / ``help``
        Show command help.
    """

    break_on: tuple[str, ...] = ("action",)
    until: str | None = None
    use_pdb: bool = False
    input_stream: TextIO = field(default_factory=lambda: sys.stdin)
    output_stream: TextIO = field(default_factory=lambda: sys.stdout)
    _armed: bool = field(default=False, init=False)
    _done_stepping: bool = field(default=False, init=False)
    last_snapshot: BacktestBarSnapshot | None = field(default=None, init=False)

    def _write(self, text: str) -> None:
        self.output_stream.write(text)
        if not text.endswith("\n"):
            self.output_stream.write("\n")
        self.output_stream.flush()

    def _read(self, prompt: str) -> str | None:
        self.output_stream.write(prompt)
        self.output_stream.flush()
        line = self.input_stream.readline()
        if line == "":
            return None
        return line.strip()

    def _until_reached(self, bar_time: str) -> bool:
        if not self.until:
            return True
        return str(bar_time or "") >= str(self.until)

    def _print_help(self) -> None:
        self._write(
            "Commands: n/next, c/continue, bar, pos, analysis, gates, "
            "actions, equity, pdb, q/quit, h/help"
        )

    def _inspect(self, cmd: str, snap: BacktestBarSnapshot) -> None:
        if cmd == "bar":
            self._write(
                f"time={snap.bar_time} open={snap.candle.get('open')} "
                f"high={snap.candle.get('high')} low={snap.candle.get('low')} "
                f"close={snap.candle.get('close')} volume={snap.candle.get('volume')}"
            )
        elif cmd == "pos":
            self._write(repr(snap.position) if snap.position else "(flat)")
        elif cmd == "analysis":
            meta = snap.analysis.metadata or {}
            self._write(
                f"direction={snap.analysis.direction} "
                f"confidence={snap.analysis.confidence} "
                f"signal={meta.get('signal')} "
                f"filters_passed={meta.get('filters_passed')}"
            )
            filters = meta.get("filters")
            if filters:
                self._write(f"filters={filters!r}")
        elif cmd == "gates":
            self._write(
                f"passed={snap.gate_passed} reasons={snap.gate_reasons} "
                f"details={snap.gate_details!r}"
            )
        elif cmd == "actions":
            if not snap.actions:
                self._write("(no actions this bar)")
            else:
                for action in snap.actions:
                    self._write(
                        f"[{action.get('sequence')}] {action.get('kind')}: "
                        f"{action.get('message')}"
                    )
        elif cmd == "equity":
            self._write(
                f"equity={snap.equity:.4f} closed_trades={snap.closed_trade_count}"
            )
        elif cmd == "pdb":
            import pdb

            # Bind snap for interactive inspection.
            pdb.set_trace()
        else:
            self._write(f"Unknown inspect command: {cmd}")

    async def __call__(self, snap: BacktestBarSnapshot) -> StepAction:
        self.last_snapshot = snap
        if self._done_stepping:
            return StepAction.CONTINUE
        if not self._until_reached(snap.bar_time):
            return StepAction.CONTINUE
        if not self._armed:
            self._armed = True
        if not snap.matches_break(self.break_on):
            return StepAction.CONTINUE

        self._write(f"— break — {snap.summary_line()}")
        if self.use_pdb:
            import pdb

            pdb.set_trace()

        while True:
            raw = self._read("backtest> ")
            if raw is None:
                # EOF: stop prompting for the rest of the run.
                self._write("EOF — continuing without further pauses")
                self._done_stepping = True
                return StepAction.CONTINUE
            cmd = raw.lower()
            if cmd in {"", "n", "next"}:
                return StepAction.CONTINUE
            if cmd in {"c", "continue"}:
                self._done_stepping = True
                return StepAction.CONTINUE
            if cmd in {"q", "quit"}:
                self._write("Cancelling backtest")
                return StepAction.CANCEL
            if cmd in {"h", "help", "?"}:
                self._print_help()
                continue
            if cmd in {"bar", "pos", "analysis", "gates", "actions", "equity", "pdb"}:
                self._inspect(cmd, snap)
                continue
            self._write(f"Unknown command {raw!r}. Type h for help.")


async def run_backtest(
    *,
    strategy_id: str | None = None,
    strategy: dict[str, Any] | None = None,
    run_id: str | None = None,
    instrument: str | None = None,
    period: str = "6m",
    account_margin: float | None = None,
    verbose: bool = False,
    name: str | None = None,
    candles_override: list[dict[str, Any]] | None = None,
    on_bar: OnBarHook | None = None,
    interactive: bool = False,
    break_on: str | Sequence[str] | None = None,
    until: str | None = None,
    use_pdb: bool = False,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    finish: bool = True,
    log: logging.Logger | None = None,
) -> dict[str, Any]:
    """Run a backtest in-process, optionally with step-through debugging.

    Parameters
    ----------
    strategy_id:
        Load strategy from Postgres and queue a new run.
    strategy:
        Ad-hoc strategy document (must include ``id``). Ignored when
        ``run_id`` is set. Useful for tests / scripted runners.
    run_id:
        Execute an existing queued run instead of creating a new one.
    instrument / period / account_margin / name / verbose:
        Queue options when creating a new run.
    candles_override:
        Skip cache/OANDA and use this candle series (oldest→newest preferred;
        the engine sorts defensively).
    on_bar:
        Optional async/sync callback invoked after each evaluation bar.
    interactive:
        Attach :class:`InteractiveBacktestDebugger` (merged with ``on_bar`` if
        both are provided — interactive runs first).
    break_on / until / use_pdb:
        Interactive debugger options.
    finish:
        When True (default), call ``finish_run`` and update strategy
        ``backtest_status`` like the worker does.

    Returns
    -------
    dict
        ``{"ok": bool, "status": str, "run_id": str, "result": engine_payload,
        "run": finished_run_or_none, "error": optional}``
    """
    break_kinds = parse_break_on(break_on)
    runs_repo = BacktestRunsRepository()

    if run_id:
        run_doc = await runs_repo.get_raw_doc(run_id)
        if run_doc is None:
            return {"ok": False, "error": f"run not found: {run_id}", "run_id": run_id}
        marked = await runs_repo.mark_running(run_id)
        if marked is None:
            return {"ok": False, "error": f"unable to mark running: {run_id}", "run_id": run_id}
        run_doc = await runs_repo.get_raw_doc(run_id) or run_doc
    else:
        strategy_doc = strategy
        if strategy_doc is None:
            if not strategy_id:
                raise ValueError("Provide strategy_id, strategy, or run_id")
            strategy_doc = await StrategiesRepository().get_by_id(strategy_id)
            if strategy_doc is None:
                return {
                    "ok": False,
                    "error": f"strategy not found: {strategy_id}",
                    "run_id": None,
                }
            await StrategiesRepository().queue_backtests([strategy_id])
        elif not strategy_doc.get("id"):
            raise ValueError("strategy document requires an 'id' field")

        period_key = normalize_backtest_period(period)
        if period_key not in BACKTEST_PERIODS:
            raise ValueError(f"Invalid period {period!r}; expected one of {sorted(BACKTEST_PERIODS)}")
        start, end = resolve_period_window(period_key)
        created = await runs_repo.create_queued_runs(
            [strategy_doc],
            name=name,
            instrument=instrument,
            period=period_key,
            verbose=verbose,
            period_start=start.isoformat(),
            period_end=end.isoformat(),
            account_margin=account_margin,
        )
        if not created:
            return {"ok": False, "error": "failed to create backtest run", "run_id": None}
        run_id = str(created[0]["id"])
        await runs_repo.mark_running(run_id)
        run_doc = await runs_repo.get_raw_doc(run_id)
        if run_doc is None:
            return {"ok": False, "error": "run disappeared after create", "run_id": run_id}

    assert run_id is not None
    verbose_flag = bool(verbose or run_doc.get("verbose"))
    if log is None:
        log, handler = attach_backtest_logger(run_id, verbose=verbose_flag)
    else:
        handler = None

    hooks: list[OnBarHook] = []
    if interactive:
        hooks.append(
            InteractiveBacktestDebugger(
                break_on=break_kinds,
                until=until,
                use_pdb=use_pdb,
                input_stream=input_stream or sys.stdin,
                output_stream=output_stream or sys.stdout,
            )
        )
    if on_bar is not None:
        hooks.append(on_bar)

    async def _combined(snap: BacktestBarSnapshot) -> StepAction:
        for hook in hooks:
            decision = hook(snap)
            if inspect.isawaitable(decision):
                decision = await decision
            if decision == StepAction.CANCEL or decision == "cancel":
                return StepAction.CANCEL
        return StepAction.CONTINUE

    strategy_id_for_status = str(run_doc.get("strategy_id") or "")

    try:
        result = await run_backtest_engine(
            run_doc,
            log=log,
            candles_override=candles_override,
            on_bar=_combined if hooks else None,
        )
        if handler is not None:
            await handler.flush_async()
        status = str(result.get("status") or BACKTEST_RUN_STATUS_COMPLETED)
        finished = None
        if finish:
            finished = await runs_repo.finish_run(
                run_id,
                status=status,
                stats=result.get("stats"),
                equity_curve=result.get("equity_curve"),
                status_message=result.get("status_message"),
            )
            if strategy_id_for_status:
                try:
                    badge = {
                        BACKTEST_RUN_STATUS_COMPLETED: BACKTEST_STATUS_COMPLETED,
                        BACKTEST_RUN_STATUS_CANCELLED: BACKTEST_STATUS_CANCELLED,
                    }.get(status, BACKTEST_STATUS_FAILED)
                    await StrategiesRepository().set_backtest_status(
                        strategy_id_for_status, badge
                    )
                except Exception:
                    logger.debug(
                        "Unable to update strategy backtest_status for %s",
                        strategy_id_for_status,
                        exc_info=True,
                    )
        return {
            "ok": status == BACKTEST_RUN_STATUS_COMPLETED,
            "status": status,
            "run_id": run_id,
            "result": result,
            "run": finished,
        }
    except Exception as exc:
        if handler is not None:
            try:
                await handler.flush_async()
            except Exception:
                pass
        log.exception("Backtest debug run failed")
        if finish:
            await runs_repo.finish_run(
                run_id,
                status=BACKTEST_RUN_STATUS_FAILED,
                error=str(exc),
                status_message="Failed",
            )
            if strategy_id_for_status:
                try:
                    await StrategiesRepository().set_backtest_status(
                        strategy_id_for_status, BACKTEST_STATUS_FAILED
                    )
                except Exception:
                    pass
        return {
            "ok": False,
            "status": BACKTEST_RUN_STATUS_FAILED,
            "run_id": run_id,
            "error": str(exc),
            "result": None,
            "run": None,
        }
    finally:
        if handler is not None:
            try:
                await handler.flush_async()
            except Exception:
                pass


__all__ = (
    "BREAK_KINDS",
    "BacktestBarSnapshot",
    "InteractiveBacktestDebugger",
    "OnBarHook",
    "StepAction",
    "parse_break_on",
    "run_backtest",
    "serialize_position",
)
