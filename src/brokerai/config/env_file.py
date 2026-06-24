"""Read/write BrokerAI environment config files."""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROD_CONFIG = Path("/etc/brokerai/config.env")
_DEV_CONFIG = _REPO_ROOT / ".env"

_UPDATE_ENV_KEYS = (
    "BROKERAI_UPDATE_TRACK",
    "BROKERAI_BRANCH",
    "BROKERAI_RELEASE",
    "BROKERAI_REPO",
    "BROKERAI_AUTO_UPDATE",
)


def config_file_path() -> Path:
    # Prefer repo .env for local dev; use prod config on installed hosts.
    if _DEV_CONFIG.exists() and not _PROD_CONFIG.exists():
        return _DEV_CONFIG
    if _PROD_CONFIG.exists():
        return _PROD_CONFIG
    return _DEV_CONFIG


def config_file_writable() -> bool:
    path = config_file_path()
    if not path.exists():
        return path.parent.exists() and os.access(path.parent, os.W_OK)
    return os.access(path, os.W_OK)


def read_env_values(path: Path, keys: tuple[str, ...]) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key in keys:
            values[key] = value.strip()
    return values


def read_update_env_values() -> dict[str, str]:
    return read_env_values(config_file_path(), _UPDATE_ENV_KEYS)


def apply_update_env_to_process(values: dict[str, str]) -> None:
    for key in _UPDATE_ENV_KEYS:
        if key in values:
            os.environ[key] = values[key]


def sync_update_env_from_file() -> None:
    apply_update_env_to_process(read_update_env_values())


def write_env_values(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines(keepends=True) if path.exists() else []
    remaining = dict(values)
    out: list[str] = []

    for line in lines:
        stripped = line.rstrip("\n")
        if "=" in stripped and not stripped.lstrip().startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}\n")
                continue
        out.append(line if line.endswith("\n") else f"{line}\n")

    for key in _UPDATE_ENV_KEYS:
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}\n")

    for key, value in remaining.items():
        out.append(f"{key}={value}\n")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(out))


def save_update_env_values(
    *,
    update_track: str,
    branch: str,
    release: str,
    repo: str,
    auto_update: bool,
) -> Path:
    path = config_file_path()
    if not config_file_writable():
        raise PermissionError(f"Config file is not writable: {path}")

    values = {
        "BROKERAI_UPDATE_TRACK": update_track,
        "BROKERAI_BRANCH": branch.strip(),
        "BROKERAI_RELEASE": release.strip(),
        "BROKERAI_REPO": repo.strip(),
        "BROKERAI_AUTO_UPDATE": "true" if auto_update else "false",
    }
    write_env_values(path, values)
    apply_update_env_to_process(values)
    return path
