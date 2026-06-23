"""Update status, logging paths, and trigger helpers for the web API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from brokerai.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_UPDATE_PROC: asyncio.subprocess.Process | None = None

_DEV_SIM_TASK: asyncio.Task[None] | None = None
_DEV_SIM: dict = {
    "status": "idle",
    "message": "",
    "step": "",
    "progress": 0,
    "log_tail": [],
}

_DEV_SIM_STEPS: list[tuple[int, str, str, str]] = [
    (5, "check", "Checking for updates…", "Checking for updates (simulated)"),
    (20, "check", "Update available", "Update available on configured track"),
    (40, "checkout", "Pulling latest code…", "Pulling latest code (simulated)"),
    (60, "deps", "Installing Python dependencies…", "Installing Python dependencies…"),
    (80, "frontend", "Building frontend…", "Building frontend…"),
    (95, "finalize", "Finalizing update…", "Finalizing simulated update…"),
]


_CACHED_CHECK: dict | None = None


def clear_update_check_cache() -> None:
    global _CACHED_CHECK
    _CACHED_CHECK = None


def repo_root() -> Path:
    return _REPO_ROOT


def is_dev_install(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return (_REPO_ROOT / ".env").exists() and not Path("/etc/brokerai/config.env").exists()


def version_lock_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    prod = Path("/opt/BrokerAI_version.txt")
    if prod.exists():
        return prod
    return settings.data_dir / "version.lock"


def update_log_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    prod = Path("/var/log/brokerai/update.log")
    if prod.exists():
        return prod
    return settings.log_dir / "update.log"


def update_state_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.data_dir / "update-state.json"


def read_version_lock(settings: Settings | None = None) -> dict[str, str]:
    path = version_lock_path(settings)
    if not path.exists():
        return {}
    raw = path.read_text().strip()
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


def installed_version_short(settings: Settings | None = None) -> str | None:
    commit = read_version_lock(settings).get("commit")
    if commit:
        return commit[:7]
    return None


def read_update_log_tail(lines: int = 30, settings: Settings | None = None) -> list[str]:
    path = update_log_path(settings)
    if not path.exists():
        return []
    try:
        return path.read_text().splitlines()[-lines:]
    except OSError:
        return []


def read_update_state(settings: Settings | None = None) -> dict:
    path = update_state_path(settings)
    if not path.exists():
        return {"status": "idle", "message": "", "step": "", "progress": 0}
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"status": "idle", "message": "", "step": "", "progress": 0}


def _dev_sim_running() -> bool:
    return _DEV_SIM_TASK is not None and not _DEV_SIM_TASK.done()


def _dev_log_line(message: str) -> str:
    return f"{datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')} {message}"


def _update_source_fields(settings: Settings) -> dict:
    return {
        "configured_pin": settings.update_pin_display,
        "update_track": settings.update_track,
        "branch": settings.branch,
        "release": settings.release or None,
        "repo": settings.repo,
        "auto_update": settings.auto_update,
    }


async def _run_dev_simulation() -> None:
    global _DEV_SIM, _CACHED_CHECK
    log: list[str] = []
    _DEV_SIM = {
        "status": "running",
        "message": "Starting simulated update…",
        "step": "check",
        "progress": 0,
        "log_tail": log,
    }

    try:
        for progress, step, message, line in _DEV_SIM_STEPS:
            await asyncio.sleep(0.85)
            log.append(_dev_log_line(line))
            _DEV_SIM.update(
                status="running",
                message=message,
                step=step,
                progress=progress,
                log_tail=log,
            )

        await asyncio.sleep(0.5)
        log.append(_dev_log_line("Simulated update complete (dev mode — no git changes applied)"))
        _CACHED_CHECK = None
        _DEV_SIM.update(
            status="success",
            message="Simulated update complete — no changes applied in dev mode",
            step="done",
            progress=100,
            log_tail=log,
        )
    except asyncio.CancelledError:
        _DEV_SIM.update(
            status="failed",
            message="Simulated update cancelled",
            step="error",
            progress=_DEV_SIM.get("progress") or 0,
            log_tail=log,
        )
        raise


async def systemd_update_active() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "is-active",
            "brokerai-update.service",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return out.decode().strip() == "active"
    except FileNotFoundError:
        return False


def background_update_running() -> bool:
    global _UPDATE_PROC
    return _UPDATE_PROC is not None and _UPDATE_PROC.returncode is None


async def fetch_check_update(settings: Settings | None = None) -> dict:
    global _CACHED_CHECK
    settings = settings or get_settings()
    script = repo_root() / "scripts" / "check-update.sh"
    if not script.exists():
        return {}

    env = os.environ.copy()
    env.update(
        {
            "BROKERAI_REPO": settings.repo,
            "BROKERAI_UPDATE_TRACK": settings.update_track,
            "BROKERAI_BRANCH": settings.branch,
            "BROKERAI_RELEASE": settings.release or "",
            "BROKERAI_INSTALL_DIR": str(repo_root()),
        }
    )
    prod_version = Path("/opt/BrokerAI_version.txt")
    env["VERSION_FILE"] = str(prod_version if prod_version.exists() else version_lock_path(settings))

    proc = await asyncio.create_subprocess_exec(
        str(script),
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(repo_root()),
        env=env,
    )
    out, stderr = await proc.communicate()
    if proc.returncode == 2:
        try:
            err = json.loads(out.decode())
            if isinstance(err, dict) and err.get("status") == "error":
                _CACHED_CHECK = err
                return err
        except json.JSONDecodeError:
            pass
    if proc.returncode not in (0, 1):
        err = stderr.decode().strip() or out.decode().strip()
        if err:
            logger.warning("check-update failed (exit %s): %s", proc.returncode, err)
        return {}
    try:
        check = json.loads(out.decode())
        if isinstance(check, dict):
            _CACHED_CHECK = check
            return check
    except json.JSONDecodeError:
        pass
    return {}


def _installed_info_from_lock(settings: Settings | None = None) -> dict[str, str]:
    lock = read_version_lock(settings)
    commit = lock.get("commit") or ""
    return {
        "track": lock.get("track") or "",
        "ref": lock.get("ref") or "",
        "commit": commit,
        "commit_short": commit[:7] if commit else "",
    }


def _resolve_installed_info(settings: Settings, resolved_check: dict | None) -> dict:
    if resolved_check and resolved_check.get("status") != "error":
        installed = resolved_check.get("installed") or {}
        if installed:
            return installed
    return _installed_info_from_lock(settings)


def _build_dev_status_payload(settings: Settings, *, check: dict | None) -> dict:
    resolved_check = check if check is not None else _CACHED_CHECK
    update_available: bool | None = None
    check_error: str | None = None
    if resolved_check:
        if resolved_check.get("status") == "error":
            check_error = str(resolved_check.get("message") or "Update check failed")
        else:
            update_available = resolved_check.get("status") == "update-available"

    installed = _resolve_installed_info(settings, resolved_check)

    status = str(_DEV_SIM.get("status") or "idle")
    if _dev_sim_running():
        status = "running"
    elif resolved_check and not check_error and not update_available and status in ("idle", "success", "up_to_date"):
        status = "up_to_date"

    default_message = "Local dev — checking uses git; applying updates is simulated only"
    if check_error:
        default_message = check_error
    elif resolved_check and not update_available and status == "up_to_date":
        default_message = "Up to date"
    elif resolved_check and update_available:
        default_message = "Update available"

    return {
        "dev_mode": True,
        "status": status,
        "message": _DEV_SIM.get("message") or default_message,
        "step": _DEV_SIM.get("step") or "",
        "progress": int(_DEV_SIM.get("progress") or 0),
        **_update_source_fields(settings),
        "installed_track": installed.get("track") or None,
        "installed_ref": installed.get("ref"),
        "installed_commit": installed.get("commit"),
        "installed_version": (installed.get("commit_short") or installed.get("commit", "")[:7] or None),
        "log_tail": list(_DEV_SIM.get("log_tail") or []),
        "check": resolved_check if resolved_check and resolved_check.get("status") != "error" else None,
        "update_available": update_available if resolved_check and not check_error else None,
        "checked": resolved_check is not None,
        "check_error": check_error,
    }


async def check_for_updates(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    check = await fetch_check_update(settings)

    if is_dev_install(settings):
        return _build_dev_status_payload(settings, check=check or None)

    return await _build_status_payload(settings, check=check or None)


async def resolve_update_status(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()

    if is_dev_install(settings):
        return _build_dev_status_payload(settings, check=_CACHED_CHECK)

    return await _build_status_payload(settings, check=_CACHED_CHECK)


async def _build_status_payload(settings: Settings, *, check: dict | None) -> dict:
    state = read_update_state(settings)
    lock = read_version_lock(settings)
    systemd_running = await systemd_update_active()
    bg_running = background_update_running()

    status = str(state.get("status") or "idle")
    if systemd_running or bg_running:
        status = "running"
    elif status == "running":
        status = "failed"
        state = {
            **state,
            "status": "failed",
            "message": state.get("message") or "Update process stopped unexpectedly",
            "progress": state.get("progress") or 0,
        }

    resolved_check = None if status == "running" else check

    update_available: bool | None = None
    check_error: str | None = None
    if resolved_check:
        if resolved_check.get("status") == "error":
            check_error = str(resolved_check.get("message") or "Update check failed")
        else:
            update_available = resolved_check.get("status") == "update-available"
            if status not in ("running", "failed") and not update_available:
                status = "up_to_date"

    message = state.get("message") or ""
    if check_error and not message:
        message = check_error

    return {
        "dev_mode": False,
        "status": status,
        "message": message,
        "step": state.get("step") or "",
        "progress": int(state.get("progress") or 0),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "error": state.get("error") or check_error,
        **_update_source_fields(settings),
        "installed_track": lock.get("track"),
        "installed_ref": lock.get("ref"),
        "installed_commit": lock.get("commit"),
        "installed_version": installed_version_short(settings),
        "log_tail": read_update_log_tail(settings=settings),
        "check": resolved_check if resolved_check and resolved_check.get("status") != "error" else None,
        "update_available": update_available,
        "checked": resolved_check is not None,
        "check_error": check_error,
    }


async def _watch_background_update(proc: asyncio.subprocess.Process) -> None:
    global _UPDATE_PROC
    await proc.wait()
    _UPDATE_PROC = None


async def start_dev_simulation() -> tuple[bool, str]:
    global _DEV_SIM_TASK

    if _dev_sim_running():
        return True, "Simulated update already in progress"

    _DEV_SIM_TASK = asyncio.create_task(_run_dev_simulation())

    def _done(task: asyncio.Task[None]) -> None:
        global _DEV_SIM_TASK
        _DEV_SIM_TASK = None
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.warning("Dev update simulation failed: %s", exc)

    _DEV_SIM_TASK.add_done_callback(_done)
    return True, "Simulated update started (dev mode)"


async def trigger_update(settings: Settings | None = None) -> tuple[bool, str]:
    settings = settings or get_settings()

    if is_dev_install(settings):
        return await start_dev_simulation()

    if background_update_running() or await systemd_update_active():
        return True, "Update already in progress"

    script = repo_root() / "scripts" / "auto-update.sh"
    commands = [
        ["sudo", "-n", "systemctl", "start", "brokerai-update.service"],
        ["sudo", "-n", str(script), "--force"],
    ]
    for cmd in commands:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True, "Update started"
            logger.warning("Update trigger failed (%s): %s", cmd, stderr.decode().strip())
        except FileNotFoundError:
            continue
    return False, "Update trigger unavailable (requires root/sudo on this host)"
