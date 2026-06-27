"""Research CLI commands."""

from __future__ import annotations

import argparse
import asyncio
import sys

from brokerai.bots.researcher.runner import (
    get_research_status,
    list_report_entries,
    read_report_content,
    run_daily_report,
    test_model_connection,
    test_news_connection,
)
from brokerai.bots.researcher.weekly import run_weekly_brief, run_weekly_debrief
from brokerai.cli.output import print_json


def _cmd_research_status(args: argparse.Namespace) -> int:
    payload = asyncio.run(get_research_status())
    if args.json:
        print_json(payload)
    else:
        print("Research status")
        print(f"  NewsAPI enabled     : {'yes' if payload['newsapi_enabled'] else 'no'}")
        print(f"  NewsAPI configured  : {'yes' if payload['newsapi_configured'] else 'no'}")
        print(f"  Data sources        : {', '.join(payload.get('data_sources_active') or []) or '—'}")
        print(f"  Analysis models     : {', '.join(payload.get('contributor_titles') or []) or '—'}")
        print(f"  Models ready        : {payload.get('contributor_count', 0)}")
        print(f"  Synthesis model     : {payload.get('synthesis_model_title') or '—'}")
        brokers = payload.get("brokers") or {}
        for key in ("forex", "metals", "stocks", "crypto", "futures", "options"):
            info = brokers.get(key) or {}
            label = info.get("label") or key.title()
            status_bits: list[str] = []
            if info.get("enabled"):
                status_bits.append("enabled")
            if info.get("implemented"):
                status_bits.append("implemented")
            if info.get("runnable"):
                status_bits.append("ready")
            count = info.get("item_count", 0)
            suffix = f" ({count} items)" if count else ""
            print(f"  {label:<18}: {', '.join(status_bits) or 'off'}{suffix}")
        print(f"  Last daily run      : {payload.get('last_daily_run_date') or '—'}")
        print(f"  Weekly brief        : {'enabled' if payload.get('weekly_brief_enabled') else 'off'}")
        print(f"  Weekly debrief      : {'enabled' if payload.get('weekly_debrief_enabled') else 'off'}")
        print(f"  Reports directory   : {payload['reports_dir']}")
        print(f"  Report count        : {payload['report_count']}")
    return 0


def _cmd_research_run_daily(args: argparse.Namespace) -> int:
    result = asyncio.run(run_daily_report(force=args.force, manual=True))
    payload = {
        "ok": result.ok,
        "report_path": result.report_path,
        "groups_processed": result.groups_processed,
        "errors": result.errors,
        "skipped_reason": result.skipped_reason,
    }
    if args.json:
        print_json(payload)
        return 0 if result.ok else (1 if result.skipped_reason else 2)
    if result.ok:
        if result.report_path:
            print(f"Daily report complete: {result.report_path}")
            if result.groups_processed:
                print(f"  Groups: {', '.join(result.groups_processed)}")
            if result.errors:
                print(f"  Warnings: {'; '.join(result.errors)}")
        elif result.skipped_reason:
            print(result.skipped_reason)
        return 0
    if result.skipped_reason:
        print(result.skipped_reason, file=sys.stderr)
        return 1
    print("; ".join(result.errors) or "Daily report failed", file=sys.stderr)
    return 2


def _cmd_research_run_weekly_brief(args: argparse.Namespace) -> int:
    result = asyncio.run(run_weekly_brief(force=args.force, manual=True))
    payload = {
        "ok": result.ok,
        "report_path": result.report_path,
        "week_key": result.week_key,
        "errors": result.errors,
        "skipped_reason": result.skipped_reason,
    }
    if args.json:
        print_json(payload)
        return 0 if result.ok else (1 if result.skipped_reason else 2)
    if result.ok and result.report_path:
        print(f"Weekly brief complete: {result.report_path}")
        return 0
    if result.skipped_reason:
        print(result.skipped_reason, file=sys.stderr)
        return 1
    print("; ".join(result.errors) or "Weekly brief failed", file=sys.stderr)
    return 2


def _cmd_research_run_weekly_debrief(args: argparse.Namespace) -> int:
    result = asyncio.run(run_weekly_debrief(force=args.force, manual=True))
    payload = {
        "ok": result.ok,
        "report_path": result.report_path,
        "week_key": result.week_key,
        "errors": result.errors,
        "skipped_reason": result.skipped_reason,
    }
    if args.json:
        print_json(payload)
        return 0 if result.ok else (1 if result.skipped_reason else 2)
    if result.ok and result.report_path:
        print(f"Weekly debrief complete: {result.report_path}")
        return 0
    if result.skipped_reason:
        print(result.skipped_reason, file=sys.stderr)
        return 1
    print("; ".join(result.errors) or "Weekly debrief failed", file=sys.stderr)
    return 2


def _cmd_research_list(args: argparse.Namespace) -> int:
    reports = list_report_entries(limit=args.limit)
    if args.json:
        print_json({"reports": reports})
    elif not reports:
        print("No research reports found.")
    else:
        for report in reports:
            print(f"{report['date']}  {report['type']:<8}  {report['filename']}")
    return 0


def _cmd_research_show(args: argparse.Namespace) -> int:
    try:
        payload = read_report_content(args.identifier)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print_json(payload)
    else:
        print(payload["content"])
    return 0


def _cmd_research_test_news(args: argparse.Namespace) -> int:
    ok, message = asyncio.run(test_news_connection())
    payload = {"ok": ok, "message": message}
    if args.json:
        print_json(payload)
    else:
        print(message)
    return 0 if ok else 1


def _cmd_research_test_model(args: argparse.Namespace) -> int:
    ok, message = asyncio.run(test_model_connection())
    payload = {"ok": ok, "message": message}
    if args.json:
        print_json(payload)
    else:
        print(message)
    return 0 if ok else 1


def register_research_commands(sub: argparse._SubParsersAction) -> None:
    research = sub.add_parser("research", help="Research reports and configuration checks")
    research_sub = research.add_subparsers(dest="research_command", required=True)

    status = research_sub.add_parser("status", help="Show research readiness")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=_cmd_research_status)

    run_daily = research_sub.add_parser("run-daily", help="Run the daily research report now")
    run_daily.add_argument("--json", action="store_true")
    run_daily.add_argument("--force", action="store_true", help="Ignore last run date guard")
    run_daily.set_defaults(func=_cmd_research_run_daily)

    run_weekly_brief = research_sub.add_parser("run-weekly-brief", help="Run the weekly opening brief now")
    run_weekly_brief.add_argument("--json", action="store_true")
    run_weekly_brief.add_argument("--force", action="store_true", help="Ignore last run week guard")
    run_weekly_brief.set_defaults(func=_cmd_research_run_weekly_brief)

    run_weekly_debrief = research_sub.add_parser(
        "run-weekly-debrief", help="Run the weekly debrief now"
    )
    run_weekly_debrief.add_argument("--json", action="store_true")
    run_weekly_debrief.add_argument("--force", action="store_true", help="Ignore last run week guard")
    run_weekly_debrief.set_defaults(func=_cmd_research_run_weekly_debrief)

    list_cmd = research_sub.add_parser("list", help="List markdown research reports")
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.add_argument("--limit", type=int, default=50)
    list_cmd.set_defaults(func=_cmd_research_list)

    show = research_sub.add_parser("show", help="Print a research report")
    show.add_argument("identifier", help="Date (YYYY-MM-DD) or filename")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=_cmd_research_show)

    test_news = research_sub.add_parser("test-news", help="Test NewsAPI connection")
    test_news.add_argument("--json", action="store_true")
    test_news.set_defaults(func=_cmd_research_test_news)

    test_model = research_sub.add_parser("test-model", help="Test selected research model")
    test_model.add_argument("--json", action="store_true")
    test_model.set_defaults(func=_cmd_research_test_model)
