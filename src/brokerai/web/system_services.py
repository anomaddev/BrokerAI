"""Service control helpers for the web API (orchestrator restart, etc.)."""

from __future__ import annotations

import asyncio
import logging
import shutil

from brokerai.config.settings import Settings, get_settings
from brokerai.core.control import ControlClient, ControlTimeout
from brokerai.web.update_runner import is_dev_install

logger = logging.getLogger(__name__)

ORCHESTRATOR_SERVICE = "brokerai-orchestrator"


async def _systemctl(*args: str) -> tuple[bool, str]:
    if shutil.which("sudo") is None:
        return False, "sudo is unavailable on this host"
    cmd = ["sudo", "-n", "systemctl", *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return False, "systemctl is unavailable on this host"
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        return True, (stdout.decode().strip() or "ok")
    detail = stderr.decode().strip() or stdout.decode().strip() or f"exit {proc.returncode}"
    return False, detail


async def trigger_orchestrator_restart(
    settings: Settings | None = None,
) -> tuple[bool, str, str]:
    """Restart the orchestrator process or, as a fallback, all in-process modules.

    Returns ``(ok, message, mode)`` where mode is ``systemd`` or ``in_process``.
    """
    settings = settings or get_settings()

    if not is_dev_install(settings):
        ok, detail = await _systemctl("restart", ORCHESTRATOR_SERVICE)
        if ok:
            return True, "Orchestrator service restart accepted", "systemd"
        logger.warning(
            "systemd restart of %s failed (%s); falling back to in-process restart",
            ORCHESTRATOR_SERVICE,
            detail,
        )

    client = ControlClient(settings)
    try:
        result = await asyncio.to_thread(
            client.submit,
            "restart",
            "orchestrator",
            timeout=45.0,
        )
    except ControlTimeout as exc:
        return False, str(exc), "in_process"

    if result.ok:
        return True, result.message or "Orchestrator modules restarted", "in_process"
    return False, result.message, "in_process"
