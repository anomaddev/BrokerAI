"""BrokerAI CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from brokerai import __version__
from brokerai.cli.helpers import (
    AUTO_UPDATE_SCRIPT,
    CHECK_UPDATE_SCRIPT,
    build_status_payload,
    read_heartbeat,
    read_version_lock,
    run_script,
    run_systemctl,
)
from brokerai.cli.output import print_bot_result, print_bots, print_help, print_json, print_status
from brokerai.cli.research import register_research_commands
from brokerai.cli.candles import register_candles_commands
from brokerai.config.settings import get_settings
from brokerai.core.control import ControlClient, ControlError, ControlTimeout
from brokerai.core.orchestrator import run_orchestrator


def _cmd_status(args: argparse.Namespace) -> int:
    payload = build_status_payload()
    if args.json:
        print_json(payload)
    else:
        print_status(payload)
    return 0


def _cmd_bots_list(args: argparse.Namespace) -> int:
    heartbeat = read_heartbeat()
    bots = heartbeat.get("bots") or [
        {"name": name, "state": "unknown"} for name in get_settings().enabled_bot_names
    ]
    if args.json:
        print_json({"bots": bots})
    else:
        print_bots(bots)
    return 0


def _cmd_bots_action(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.name not in settings.enabled_bot_names:
        print(f"Unknown bot '{args.name}'. Enabled: {', '.join(settings.enabled_bot_names)}", file=sys.stderr)
        return 1
    client = ControlClient()
    try:
        result = client.submit(args.action, args.name, timeout=args.timeout)
    except ControlTimeout as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ControlError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = {
        "ok": result.ok,
        "action": result.action,
        "bot": result.bot,
        "message": result.message,
        "bot_status": result.bot_status,
    }
    if args.json:
        print_json(payload)
    else:
        print_bot_result(payload)
    return 0 if result.ok else 1


def _cmd_update_check(args: argparse.Namespace) -> int:
    script_args = ["--json"] if args.json else []
    if args.quiet:
        script_args.append("--quiet")
    return run_script(CHECK_UPDATE_SCRIPT, *script_args)


def _cmd_update_apply(_: argparse.Namespace) -> int:
    from brokerai.cli.helpers import resolve_script

    if resolve_script(AUTO_UPDATE_SCRIPT):
        return run_script(AUTO_UPDATE_SCRIPT, "--force")
    return run_systemctl("start", "brokerai-update.service")


def _cmd_services_status(_: argparse.Namespace) -> int:
    return run_systemctl("status", "brokerai-orchestrator", "brokerai-web", "--no-pager")


def _cmd_services_restart(_: argparse.Namespace) -> int:
    code = run_systemctl("restart", "brokerai-orchestrator", "brokerai-web")
    if code == 0:
        print("Restarted brokerai-orchestrator and brokerai-web")
    return code


def _cmd_run_orchestrator(_: argparse.Namespace) -> int:
    asyncio.run(run_orchestrator())
    return 0


def _cmd_version(args: argparse.Namespace) -> int:
    lock = read_version_lock()
    payload = {
        "package_version": __version__,
        "installed_commit": lock.get("commit"),
        "installed_track": lock.get("track"),
        "installed_ref": lock.get("ref"),
    }
    if args.json:
        print_json(payload)
    else:
        print(f"brokerai {__version__}")
        if lock.get("commit"):
            pin = f"{lock.get('track', '?')}:{lock.get('ref', '?')}"
            print(f"  installed: {pin} @ {lock['commit'][:7]}")
    return 0


def _cmd_help(args: argparse.Namespace) -> int:
    print_help(__version__, args.topic)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brokerai",
        description="BrokerAI — trading bot control CLI",
        add_help=True,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    help_cmd = sub.add_parser("help", help="Show help")
    help_cmd.add_argument("topic", nargs="?", help="Command group (status, bots, update, services, run, version, research)")
    help_cmd.set_defaults(func=_cmd_help)

    status = sub.add_parser("status", help="Show orchestrator and bot status")
    status.add_argument("--json", action="store_true", help="Output JSON")
    status.set_defaults(func=_cmd_status)

    bots = sub.add_parser("bots", help="List or control sub-bots")
    bots_sub = bots.add_subparsers(dest="bots_command", required=True)

    bots_list = bots_sub.add_parser("list", help="List bot statuses")
    bots_list.add_argument("--json", action="store_true")
    bots_list.set_defaults(func=_cmd_bots_list)

    for action in ("start", "stop"):
        cmd = bots_sub.add_parser(action, help=f"{action.capitalize()} a sub-bot")
        cmd.add_argument("name", help="Bot name (research, execution, analysis)")
        cmd.add_argument("--json", action="store_true")
        cmd.add_argument("--timeout", type=float, default=5.0, help="IPC timeout in seconds")
        cmd.set_defaults(func=_cmd_bots_action, action=action)

    update = sub.add_parser("update", help="Check or apply updates")
    update_sub = update.add_subparsers(dest="update_command", required=True)

    update_check = update_sub.add_parser("check", help="Check for available updates")
    update_check.add_argument("--json", action="store_true")
    update_check.add_argument("--quiet", action="store_true")
    update_check.set_defaults(func=_cmd_update_check)

    update_apply = update_sub.add_parser("apply", help="Apply updates now")
    update_apply.set_defaults(func=_cmd_update_apply)

    services = sub.add_parser("services", help="Manage systemd services")
    services_sub = services.add_subparsers(dest="services_command", required=True)

    services_status = services_sub.add_parser("status", help="Show service status")
    services_status.set_defaults(func=_cmd_services_status)

    services_restart = services_sub.add_parser("restart", help="Restart orchestrator and web UI")
    services_restart.set_defaults(func=_cmd_services_restart)

    run = sub.add_parser("run", help="Run internal processes")
    run_sub = run.add_subparsers(dest="run_target", required=True)
    run_orch = run_sub.add_parser("orchestrator", help="Run the orchestrator (systemd)")
    run_orch.set_defaults(func=_cmd_run_orchestrator)

    register_research_commands(sub)
    register_candles_commands(sub)

    version = sub.add_parser("version", help="Show version information")
    version.add_argument("--json", action="store_true")
    version.set_defaults(func=_cmd_version)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        print_help(__version__)
        sys.exit(0)
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
