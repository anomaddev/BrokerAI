"""Shared helpers for CLI commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from brokerai import __version__
from brokerai.config.settings import get_settings

INSTALL_DIR = Path("/opt/brokerai")
VERSION_FILE = Path("/opt/BrokerAI_version.txt")
CHECK_UPDATE_SCRIPT = INSTALL_DIR / "scripts" / "check-update.sh"
AUTO_UPDATE_SCRIPT = INSTALL_DIR / "scripts" / "auto-update.sh"


def read_heartbeat() -> dict[str, Any]:
    path = get_settings().data_dir / "heartbeat.json"
    if not path.exists():
        return {"running": False, "bots": [], "timestamp": None}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"running": False, "bots": [], "timestamp": None}


def read_version_lock() -> dict[str, str]:
    if not VERSION_FILE.exists():
        return {}
    raw = VERSION_FILE.read_text().strip()
    if not raw:
        return {}
    if "=" in raw:
        lock: dict[str, str] = {}
        for line in raw.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                lock[key.strip()] = value.strip()
        return lock
    return {"commit": raw}


def build_status_payload() -> dict[str, Any]:
    settings = get_settings()
    heartbeat = read_heartbeat()
    lock = read_version_lock()
    installed_pin = None
    if lock.get("track"):
        installed_pin = f"{lock.get('track')}:{lock.get('ref', '?')}"
    return {
        "version": __version__,
        "orchestrator_running": heartbeat.get("running", False),
        "heartbeat_timestamp": heartbeat.get("timestamp"),
        "bots": heartbeat.get("bots", []),
        "enabled_bots": settings.enabled_bot_names,
        "configured_pin": settings.update_pin_display,
        "installed_pin": installed_pin,
        "installed_commit": (lock.get("commit") or "")[:7] or None,
        "auto_update": settings.auto_update,
        "update_track": settings.update_track,
    }


def resolve_script(script: Path) -> Path | None:
    if script.exists():
        return script
    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root / "scripts" / script.name
    if candidate.exists():
        return candidate
    return None


def run_script(script: Path, *args: str) -> int:
    resolved = resolve_script(script)
    if resolved is None:
        print(f"Script not found: {script}", file=sys.stderr)
        return 2
    result = subprocess.run([str(resolved), *args], check=False)
    return result.returncode


def run_systemctl(*args: str) -> int:
    result = subprocess.run(["systemctl", *args], check=False)
    return result.returncode
