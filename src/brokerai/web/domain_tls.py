"""Apply public HTTPS domains via privileged host script."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path

from brokerai.config.env_file import (
    config_file_path,
    config_file_writable,
    read_env_values,
    write_env_values,
)
from brokerai.config.settings import Settings, get_settings
from brokerai.web.update_runner import is_dev_install

logger = logging.getLogger(__name__)

_DOMAIN_ENV_KEYS = (
    "BROKERAI_DOMAIN",
    "BROKERAI_SUPABASE_DOMAIN",
    "BROKERAI_SUPABASE_URL",
)

_HOSTNAME_RE = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$"
)

_APPLY_SCRIPT = Path("/opt/brokerai/scripts/apply-domain-tls.sh")


def valid_hostname(value: str) -> bool:
    value = value.strip()
    if not value or "." not in value or len(value) > 253:
        return False
    return bool(_HOSTNAME_RE.fullmatch(value))


def read_domain_settings() -> dict[str, str]:
    values = read_env_values(config_file_path(), _DOMAIN_ENV_KEYS)
    return {
        "domain": values.get("BROKERAI_DOMAIN", "").strip(),
        "supabase_domain": values.get("BROKERAI_SUPABASE_DOMAIN", "").strip(),
        "supabase_url": values.get("BROKERAI_SUPABASE_URL", "").strip(),
    }


def domain_tls_apply_available(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if is_dev_install(settings):
        return config_file_writable()
    return _APPLY_SCRIPT.is_file() and shutil.which("sudo") is not None


async def apply_domain_tls(
    *,
    domain: str,
    supabase_domain: str = "",
    settings: Settings | None = None,
) -> tuple[bool, str]:
    """Persist domains and apply host Caddy TLS.

    Production uses sudo + apply-domain-tls.sh. Local/dev writes the env file only.
    """
    settings = settings or get_settings()
    domain = domain.strip()
    supabase_domain = supabase_domain.strip()

    if not valid_hostname(domain):
        return False, "Enter a valid hostname (e.g. broker.example.com)"
    if supabase_domain and not valid_hostname(supabase_domain):
        return False, "Enter a valid Supabase hostname (e.g. supabase.example.com)"

    if is_dev_install(settings):
        return _apply_domain_dev(domain=domain, supabase_domain=supabase_domain)

    if not _APPLY_SCRIPT.is_file():
        return False, f"Apply script missing: {_APPLY_SCRIPT}"

    cmd = [
        "sudo",
        "-n",
        str(_APPLY_SCRIPT),
        "--domain",
        domain,
    ]
    if supabase_domain:
        cmd.extend(["--supabase-domain", supabase_domain])
    else:
        cmd.append("--clear-supabase")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return False, "sudo is not available on this host"

    stdout, stderr = await proc.communicate()
    out = stdout.decode().strip()
    err = stderr.decode().strip()
    if proc.returncode != 0:
        detail = err or out or f"exit {proc.returncode}"
        logger.error("apply-domain-tls failed: %s", detail)
        return False, detail

    message = out or f"HTTPS ready for https://{domain}"
    if supabase_domain:
        message = f"{message}\nhttps://{supabase_domain} (Kong + Studio)"
    return True, message


def _apply_domain_dev(*, domain: str, supabase_domain: str) -> tuple[bool, str]:
    path = config_file_path()
    if not config_file_writable():
        return False, f"Cannot write {path}"

    values = {
        "BROKERAI_DOMAIN": domain,
        "BROKERAI_WEB_BIND": "127.0.0.1",
        "BROKERAI_SESSION_COOKIE_SECURE": "true",
    }
    if supabase_domain:
        values["BROKERAI_SUPABASE_DOMAIN"] = supabase_domain
        values["BROKERAI_SUPABASE_URL"] = f"https://{supabase_domain}"
    else:
        values["BROKERAI_SUPABASE_DOMAIN"] = ""
        values["BROKERAI_SUPABASE_URL"] = "http://127.0.0.1:8000"

    write_env_values(path, values)
    for key, value in values.items():
        if value:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]

    note = (
        f"Saved to {path}. Local/dev does not install Caddy — "
        f"on a Proxmox/LXC host use Apply to enable HTTPS."
    )
    return True, note
