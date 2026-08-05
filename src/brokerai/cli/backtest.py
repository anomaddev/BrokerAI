"""CLI commands for running and debugging strategy backtests."""

from __future__ import annotations

import argparse
import asyncio
import sys

from brokerai.backtesting.debug import BREAK_KINDS, parse_break_on, run_backtest
from brokerai.cli.output import print_json
from brokerai.db.pg.client import close_pg, init_pg
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_PERIODS,
    BacktestRunsRepository,
)
from brokerai.db.repositories.strategies import StrategiesRepository


def _run(coro) -> int:
    return asyncio.run(coro)


async def _with_pg(coro_factory):
    await init_pg()
    try:
        return await coro_factory()
    finally:
        try:
            await close_pg()
        except Exception:
            pass


async def _cmd_strategies(args: argparse.Namespace) -> int:
    async def _inner() -> int:
        rows = await StrategiesRepository().list_all()
        payload = [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "timeframe": row.get("timeframe"),
                "instruments": row.get("instruments") or [],
                "enabled": row.get("enabled"),
                "backtest_status": row.get("backtest_status"),
            }
            for row in rows
        ]
        if args.json:
            print_json({"strategies": payload})
            return 0
        if not payload:
            print("No strategies found.")
            return 0
        for row in payload:
            instruments = ", ".join(row["instruments"]) or "—"
            print(
                f"{row['id']}  {row['name']}  tf={row['timeframe']}  "
                f"instruments={instruments}  enabled={row['enabled']}  "
                f"backtest={row['backtest_status']}"
            )
        return 0

    return await _with_pg(_inner)


async def _cmd_list(args: argparse.Namespace) -> int:
    async def _inner() -> int:
        runs = await BacktestRunsRepository().list_runs(
            strategy_id=args.strategy_id,
            status=args.status,
            limit=args.limit,
        )
        if args.json:
            print_json({"runs": runs})
            return 0
        if not runs:
            print("No backtest runs found.")
            return 0
        for run in runs:
            stats = run.get("stats") or {}
            print(
                f"{run.get('id')}  {run.get('status')}  "
                f"{run.get('strategy_name') or run.get('strategy_id')}  "
                f"{run.get('instrument')}  period={run.get('period')}  "
                f"trades={stats.get('total_trades')}  "
                f"pnl={stats.get('realized_pnl')}"
            )
        return 0

    return await _with_pg(_inner)


async def _cmd_show(args: argparse.Namespace) -> int:
    async def _inner() -> int:
        run = await BacktestRunsRepository().get_by_id(args.run_id)
        if run is None:
            print(f"Backtest run not found: {args.run_id}", file=sys.stderr)
            return 1
        if args.json:
            print_json(run)
            return 0
        stats = run.get("stats") or {}
        print(f"id            : {run.get('id')}")
        print(f"name          : {run.get('name')}")
        print(f"status        : {run.get('status')}")
        print(f"strategy      : {run.get('strategy_name')} ({run.get('strategy_id')})")
        print(f"instrument    : {run.get('instrument')}")
        print(f"timeframe     : {run.get('timeframe')}")
        print(f"period        : {run.get('period')}")
        print(f"progress      : {run.get('progress_pct')}%")
        print(f"message       : {run.get('status_message')}")
        print(f"trades        : {stats.get('total_trades')}")
        print(f"win rate      : {stats.get('win_rate')}")
        print(f"realized pnl  : {stats.get('realized_pnl')}")
        print(f"max drawdown  : {stats.get('max_drawdown')}")
        if run.get("error"):
            print(f"error         : {run.get('error')}")
        return 0

    return await _with_pg(_inner)


async def _cmd_run(args: argparse.Namespace) -> int:
    if not args.run_id and not args.strategy_id:
        print("Provide --strategy-id or --run-id", file=sys.stderr)
        return 2

    try:
        break_on = parse_break_on(args.break_on)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    interactive = bool(args.step or args.pdb)

    async def _inner() -> int:
        result = await run_backtest(
            strategy_id=args.strategy_id,
            run_id=args.run_id,
            instrument=args.instrument,
            period=args.period,
            account_margin=args.margin,
            verbose=args.verbose,
            name=args.name,
            interactive=interactive,
            break_on=break_on,
            until=args.until,
            use_pdb=args.pdb,
        )
        if args.json:
            # Strip non-JSON-friendly nested objects; keep summary fields.
            payload = {
                "ok": result.get("ok"),
                "status": result.get("status"),
                "run_id": result.get("run_id"),
                "error": result.get("error"),
                "stats": (result.get("result") or {}).get("stats"),
                "run": result.get("run"),
            }
            print_json(payload)
        else:
            if result.get("error") and not result.get("ok"):
                print(f"Backtest failed: {result['error']}", file=sys.stderr)
            else:
                stats = (result.get("result") or {}).get("stats") or {}
                print(
                    f"Backtest {result.get('status')}: run_id={result.get('run_id')} "
                    f"trades={stats.get('total_trades')} "
                    f"pnl={stats.get('realized_pnl')} "
                    f"win_rate={stats.get('win_rate')} "
                    f"max_dd={stats.get('max_drawdown')}"
                )
        if not result.get("ok"):
            return 1 if result.get("status") != "cancelled" else 130
        return 0

    return await _with_pg(_inner)


def register_backtest_commands(sub: argparse._SubParsersAction) -> None:
    backtest = sub.add_parser("backtest", help="Run and debug strategy backtests")
    backtest_sub = backtest.add_subparsers(dest="backtest_command", required=True)

    strategies = backtest_sub.add_parser("strategies", help="List strategies")
    strategies.add_argument("--json", action="store_true")
    strategies.set_defaults(func=lambda args: _run(_cmd_strategies(args)))

    list_cmd = backtest_sub.add_parser("list", help="List recent backtest runs")
    list_cmd.add_argument("--strategy-id", help="Filter by strategy id")
    list_cmd.add_argument("--status", help="Filter by status (queued, running, …)")
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.set_defaults(func=lambda args: _run(_cmd_list(args)))

    show = backtest_sub.add_parser("show", help="Show one backtest run")
    show.add_argument("run_id", help="Backtest run id")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=lambda args: _run(_cmd_show(args)))

    run = backtest_sub.add_parser(
        "run",
        help="Run a backtest in-process (optionally step-through debug)",
    )
    run.add_argument("--strategy-id", help="Strategy id to queue and run")
    run.add_argument("--run-id", help="Existing queued run id to execute")
    run.add_argument("--instrument", help="Forex pair, e.g. EUR/USD")
    run.add_argument(
        "--period",
        default="6m",
        choices=sorted(BACKTEST_PERIODS),
        help="Evaluation period window",
    )
    run.add_argument("--margin", type=float, default=None, help="Account margin (USD)")
    run.add_argument("--name", help="Optional run label")
    run.add_argument("--verbose", action="store_true", help="DEBUG backtest logs")
    run.add_argument(
        "--step",
        action="store_true",
        help="Interactive step-through REPL on break-on events",
    )
    run.add_argument(
        "--break-on",
        default="action",
        help=(
            "Comma-separated pause kinds for --step: "
            + ", ".join(sorted(BREAK_KINDS))
            + " (default: action)"
        ),
    )
    run.add_argument(
        "--until",
        help="ISO/OANDA bar time — ignore breaks until this open time",
    )
    run.add_argument(
        "--pdb",
        action="store_true",
        help="Drop into pdb at each break (implies --step)",
    )
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=lambda args: _run(_cmd_run(args)))
