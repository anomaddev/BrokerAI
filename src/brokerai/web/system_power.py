"""Host reboot and shutdown helpers for the web API."""

from __future__ import annotations

import asyncio
import logging
import shutil

from brokerai.config.settings import Settings, get_settings
from brokerai.web.update_runner import is_dev_install

logger = logging.getLogger(__name__)

_REBOOT_COMMANDS = (
    ["sudo", "-n", "systemctl", "reboot"],
    ["sudo", "-n", "/sbin/reboot"],
    ["sudo", "-n", "reboot"],
)

_SHUTDOWN_COMMANDS = (
    ["sudo", "-n", "systemctl", "poweroff"],
    ["sudo", "-n", "/sbin/shutdown", "-h", "now"],
    ["sudo", "-n", "shutdown", "-h", "now"],
)


def power_control_available(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if is_dev_install(settings):
        return False
    return shutil.which("sudo") is not None


async def _run_power_command(commands: tuple[list[str], ...]) -> tuple[bool, str]:
    for cmd in commands:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True, "accepted"
            logger.warning("Power command failed (%s): %s", cmd, stderr.decode().strip())
        except FileNotFoundError:
            continue
    return False, "Power control unavailable (requires root/sudo on this host)"


async def _schedule_power_command(commands: tuple[list[str], ...]) -> None:
    await asyncio.sleep(1.5)
    ok, message = await _run_power_command(commands)
    if not ok:
        logger.error("Scheduled power command failed: %s", message)


async def trigger_reboot(settings: Settings | None = None) -> tuple[bool, str]:
    settings = settings or get_settings()
    if is_dev_install(settings):
        return False, "Reboot is disabled in local development"
    if not power_control_available(settings):
        return False, "Reboot is unavailable on this host"

    asyncio.create_task(_schedule_power_command(_REBOOT_COMMANDS))
    return True, "Reboot initiated"


async def trigger_shutdown(settings: Settings | None = None) -> tuple[bool, str]:
    settings = settings or get_settings()
    if is_dev_install(settings):
        return False, "Shutdown is disabled in local development"
    if not power_control_available(settings):
        return False, "Shutdown is unavailable on this host"

    asyncio.create_task(_schedule_power_command(_SHUTDOWN_COMMANDS))
    return True, "Shutdown initiated"
