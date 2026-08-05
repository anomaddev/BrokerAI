"""CLI output formatters."""

from __future__ import annotations

import json
from typing import Any


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def print_status(data: dict[str, Any]) -> None:
    running = "running" if data.get("orchestrator_running") else "offline"
    print(f"BrokerAI {running}")
    print(f"  Version     : {data.get('version')}")
    if data.get("installed_commit"):
        print(f"  Installed   : {data.get('installed_pin', '?')} @ {data['installed_commit']}")
    if data.get("configured_pin"):
        print(f"  Update pin  : {data.get('configured_pin')}")
    print(f"  Enabled bots: {', '.join(data.get('enabled_bots', []))}")
    if data.get("heartbeat_timestamp"):
        print(f"  Heartbeat   : {data['heartbeat_timestamp']}")


def print_bots(bots: list[dict[str, Any]]) -> None:
    if not bots:
        print("No bots configured.")
        return
    name_width = max(len(b["name"]) for b in bots)
    for bot in bots:
        state = bot.get("state", "unknown")
        line = f"  {bot['name']:<{name_width}}  {state}"
        if bot.get("started_at"):
            line += f"  (since {bot['started_at']})"
        print(line)


def print_bot_result(result: dict[str, Any]) -> None:
    status = "ok" if result.get("ok") else "failed"
    print(f"{result.get('action')} {result.get('bot')}: {status} — {result.get('message')}")
    if result.get("bot_status"):
        print(f"  state: {result['bot_status'].get('state')}")


def print_help(version: str, topic: str | None = None) -> None:
    if topic:
        topics = {
            "status": "brokerai status [--json]",
            "bots": "\n".join(
                [
                    "brokerai bots list [--json]",
                    "brokerai bots start <name> [--json] [--timeout SECS]",
                    "brokerai bots stop <name> [--json] [--timeout SECS]",
                ]
            ),
            "update": "\n".join(
                [
                    "brokerai update check [--json] [--quiet]",
                    "brokerai update apply",
                ]
            ),
            "services": "\n".join(
                [
                    "brokerai services status",
                    "brokerai services restart",
                ]
            ),
            "run": "\n".join(
                [
                    "brokerai run orchestrator",
                    "brokerai run data-manager [--interval SECS] [--once]",
                ]
            ),
            "version": "brokerai version [--json]",
            "research": "\n".join(
                [
                    "brokerai research status [--json]",
                    "brokerai research run-daily [--json] [--force]",
                    "brokerai research list [--json] [--limit N]",
                    "brokerai research show <date|file> [--json]",
                    "brokerai research test-news [--json]",
                    "brokerai research test-model [--json]",
                ]
            ),
            "candles": "\n".join(
                [
                    "brokerai candles sync --symbol PAIR --timeframe TF [--json]",
                    "brokerai candles backfill --symbol PAIR --timeframe TF --start DATE [--end DATE]",
                    "brokerai candles status [--symbol PAIR] [--timeframe TF] [--json]",
                ]
            ),
            "backtest": "\n".join(
                [
                    "brokerai backtest strategies [--json]",
                    "brokerai backtest list [--strategy-id ID] [--status STATUS] [--limit N] [--json]",
                    "brokerai backtest show <run_id> [--json]",
                    "brokerai backtest run --strategy-id ID [--instrument PAIR] [--period 1m|3m|6m|1y|2y|5y]",
                    "                     [--margin USD] [--name LABEL] [--verbose] [--json]",
                    "                     [--step] [--break-on action,signal,entry,exit,bar,filter_fail]",
                    "                     [--until TIME] [--pdb]",
                    "brokerai backtest run --run-id ID [--step] [--break-on …] [--pdb]",
                ]
            ),
        }
        detail = topics.get(topic)
        if detail is None:
            print(f"Unknown help topic: {topic}")
            print(f"Topics: {', '.join(sorted(topics))}")
            return
        print(f"brokerai {topic}\n")
        print(detail)
        return

    print(f"""BrokerAI {version} — trading bot control CLI

Usage:
  brokerai <command> [options]

Commands:
  status              Show orchestrator and bot status
  bots list           List sub-bot states
  bots start <name>   Start a sub-bot (research, execution, analysis)
  bots stop <name>    Stop a sub-bot
  research status     Show research configuration readiness
  research run-daily  Run daily research report now
  research list       List markdown research reports
  research show       Print a research report
  research test-news  Test NewsAPI connection
  research test-model Test selected research model
  backtest strategies List strategies available for backtests
  backtest list       List recent backtest runs
  backtest show       Show one backtest run
  backtest run        Run a backtest in-process (optional --step / --pdb)
  update check        Check for available updates (exit 1 if available)
  update apply        Apply updates now (requires root)
  services status     Show systemd service status
  services restart    Restart orchestrator and web UI (requires root)
  version             Show package and installed version
  run orchestrator    Run orchestrator process (used by systemd)
  run data-manager    Run data manager tick loop for development
  help [topic]        Show this help or help for a command group

Examples:
  brokerai status
  brokerai bots list
  brokerai bots stop research
  brokerai research run-daily --force
  brokerai backtest run --strategy-id <id> --instrument EUR/USD --period 1m --step
  brokerai backtest run --strategy-id <id> --break-on signal,entry,exit --step
  brokerai run data-manager --interval 10
  brokerai run data-manager --once
  brokerai update check
  sudo brokerai update apply
  brokerai help bots
  brokerai help backtest

Notes:
  Bot control requires the orchestrator to be running.
  Config: /etc/brokerai/config.env (container) or .env (local dev)
  Web UI: http://<host>:1989
""")
