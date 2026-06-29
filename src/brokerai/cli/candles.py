"""CLI commands for candle cache management."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from brokerai.bots.data_manager.service import DataManagerService
from brokerai.cli.output import print_json
from brokerai.config.settings import get_settings


def _service() -> DataManagerService:
    return DataManagerService.create_standalone()


async def _cmd_sync(args: argparse.Namespace) -> int:
    service = _service()
    result = await service.sync(
        args.symbol,
        args.timeframe,
        bar_count=args.bar_count,
        incremental=args.incremental,
    )
    payload = result.model_dump()
    if args.json:
        print_json(payload)
    else:
        if result.error:
            print(f"Sync failed: {result.error}", file=sys.stderr)
        else:
            print(
                f"Synced {args.symbol} {args.timeframe}: "
                f"{result.upserted} candle(s), complete={result.complete}"
            )
    return 1 if result.error else 0


async def _cmd_backfill(args: argparse.Namespace) -> int:
    service = _service()
    result = await service.backfill(
        args.symbol,
        args.timeframe,
        args.start,
        args.end or datetime.now(timezone.utc).date().isoformat(),
    )
    payload = result.model_dump()
    if args.json:
        print_json(payload)
    else:
        if result.error:
            print(f"Backfill failed: {result.error}", file=sys.stderr)
        else:
            print(
                f"Backfilled {args.symbol} {args.timeframe}: "
                f"{result.upserted} candle(s) in {result.chunks} chunk(s)"
            )
    return 1 if result.error else 0


async def _cmd_verify(args: argparse.Namespace) -> int:
    service = _service()
    result = await service.verify(args.symbol, args.timeframe, days=args.days)
    payload = result.model_dump()
    if args.json:
        print_json(payload)
    else:
        print(
            f"Verify {args.symbol} {args.timeframe} ({args.days}d): "
            f"missing={result.missing_count}, complete={result.complete}"
        )
        if result.missing_times[:5]:
            print("Sample missing:", ", ".join(result.missing_times[:5]))
    return 0 if result.complete else 1


async def _cmd_repair(args: argparse.Namespace) -> int:
    service = _service()
    result = await service.repair(args.symbol, args.timeframe, days=args.days)
    payload = result.model_dump()
    if args.json:
        print_json(payload)
    else:
        if result.error:
            print(f"Repair failed: {result.error}", file=sys.stderr)
        else:
            print(
                f"Repaired {args.symbol} {args.timeframe}: "
                f"{result.upserted} candle(s), complete={result.complete}"
            )
    return 1 if result.error else 0


async def _cmd_status(args: argparse.Namespace) -> int:
    service = _service()
    settings = get_settings()
    symbols = None
    if args.symbol and args.timeframe:
        symbols = [(args.symbol, args.timeframe)]
    rows = await service.status(symbols=symbols)
    payload = [row.model_dump() for row in rows]
    if args.json:
        print_json({"candles": payload, "default_timeframes": settings.candle_default_timeframes})
    else:
        if not payload:
            print("No candle sync state found.")
            return 0
        for row in payload:
            print(
                f"{row['symbol']} {row['timeframe']}: count={row['count']} "
                f"latest={row['latest_time']} complete={row['complete']}"
            )
    return 0


def _run(coro) -> int:
    return asyncio.run(coro)


def register_candles_commands(sub: argparse._SubParsersAction) -> None:
    candles = sub.add_parser("candles", help="Manage OANDA candle cache")
    candles_sub = candles.add_subparsers(dest="candles_command", required=True)

    sync = candles_sub.add_parser("sync", help="Sync candles for a symbol/timeframe")
    sync.add_argument("--symbol", required=True, help="Forex pair, e.g. EUR/USD")
    sync.add_argument("--timeframe", required=True, help="Timeframe, e.g. M15")
    sync.add_argument("--bar-count", type=int, default=None, help="Bootstrap bar count")
    sync.add_argument("--incremental", action="store_true", help="Incremental sync only")
    sync.add_argument("--json", action="store_true")
    sync.set_defaults(func=lambda args: _run(_cmd_sync(args)))

    backfill = candles_sub.add_parser("backfill", help="Backfill a date range")
    backfill.add_argument("--symbol", required=True)
    backfill.add_argument("--timeframe", required=True)
    backfill.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    backfill.add_argument("--end", help="End date YYYY-MM-DD (default: today)")
    backfill.add_argument("--json", action="store_true")
    backfill.set_defaults(func=lambda args: _run(_cmd_backfill(args)))

    verify = candles_sub.add_parser("verify", help="Verify cache completeness")
    verify.add_argument("--symbol", required=True)
    verify.add_argument("--timeframe", required=True)
    verify.add_argument("--days", type=int, default=30)
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=lambda args: _run(_cmd_verify(args)))

    repair = candles_sub.add_parser("repair", help="Repair missing candles")
    repair.add_argument("--symbol", required=True)
    repair.add_argument("--timeframe", required=True)
    repair.add_argument("--days", type=int, default=30)
    repair.add_argument("--json", action="store_true")
    repair.set_defaults(func=lambda args: _run(_cmd_repair(args)))

    status = candles_sub.add_parser("status", help="Show cache status")
    status.add_argument("--symbol", help="Optional symbol filter")
    status.add_argument("--timeframe", help="Optional timeframe filter")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=lambda args: _run(_cmd_status(args)))
