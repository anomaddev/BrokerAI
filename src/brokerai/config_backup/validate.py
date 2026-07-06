from __future__ import annotations

import json
from typing import Any

from brokerai.db.repositories.config_backups import SCHEMA_VERSION

MAX_IMPORT_BYTES = 10 * 1024 * 1024

REQUIRED_PAYLOAD_KEYS = (
    "schema_version",
    "user_preferences",
    "system_settings",
    "asset_settings",
    "strategies",
    "exchange_connections",
    "research_settings",
    "data_connections",
    "ai_models",
)


def parse_import_bytes(raw: bytes) -> dict[str, Any]:
    """Parse and validate uploaded backup JSON bytes."""
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValueError(f"Backup file exceeds {MAX_IMPORT_BYTES // (1024 * 1024)} MB limit")

    if not raw.strip():
        raise ValueError("Backup file is empty")

    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Backup file must be valid UTF-8 JSON") from exc

    if not isinstance(document, dict):
        raise ValueError("Backup JSON must be an object")

    payload = document.get("payload") if "payload" in document else document
    if not isinstance(payload, dict):
        raise ValueError("Backup payload must be an object")

    return validate_payload(payload)


def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a backup payload structure and return a normalized copy."""
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported backup schema version: {schema_version}")

    normalized: dict[str, Any] = {"schema_version": SCHEMA_VERSION}

    prefs = payload.get("user_preferences")
    if prefs is not None and not isinstance(prefs, dict):
        raise ValueError("user_preferences must be an object or null")
    normalized["user_preferences"] = prefs

    system = payload.get("system_settings")
    if system is not None and not isinstance(system, dict):
        raise ValueError("system_settings must be an object or null")
    normalized["system_settings"] = system

    for key in ("asset_settings", "strategies", "exchange_connections", "data_connections", "ai_models"):
        value = payload.get(key)
        if value is None:
            normalized[key] = []
        elif not isinstance(value, list):
            raise ValueError(f"{key} must be an array")
        else:
            normalized[key] = list(value)

    research = payload.get("research_settings")
    if research is not None and not isinstance(research, dict):
        raise ValueError("research_settings must be an object or null")
    normalized["research_settings"] = research

    if not _has_meaningful_content(normalized):
        raise ValueError("Backup payload contains no configuration data")

    return normalized


def _has_meaningful_content(payload: dict[str, Any]) -> bool:
    if payload.get("user_preferences"):
        return True
    if payload.get("system_settings"):
        return True
    if any(payload.get(key) for key in ("asset_settings", "strategies", "exchange_connections", "data_connections", "ai_models")):
        return True
    if payload.get("research_settings"):
        return True
    return False
