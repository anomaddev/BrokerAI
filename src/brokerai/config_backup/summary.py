from __future__ import annotations

from typing import Any


def summarize_payload(payload: dict[str, Any]) -> list[str]:
    """Return human-readable settings areas included in a backup payload."""
    areas: list[str] = []

    prefs = payload.get("user_preferences") or {}
    if prefs.get("general_settings"):
        areas.append("General")
    if prefs.get("market_indicators"):
        areas.append("Display")

    system = payload.get("system_settings")
    if isinstance(system, dict) and system:
        areas.append("System updates")

    asset_settings = list(payload.get("asset_settings") or [])
    enabled_assets = [doc.get("asset_class") for doc in asset_settings if doc.get("enabled")]
    if asset_settings:
        if enabled_assets:
            areas.append(f"Broker ({', '.join(str(a) for a in enabled_assets)})")
        else:
            areas.append("Broker")

    strategies = list(payload.get("strategies") or [])
    if strategies:
        areas.append(f"Strategies ({len(strategies)})")

    exchange_connections = list(payload.get("exchange_connections") or [])
    if exchange_connections:
        areas.append(f"Exchanges ({len(exchange_connections)})")

    if payload.get("research_settings"):
        areas.append("Research")

    data_connections = list(payload.get("data_connections") or [])
    if data_connections:
        areas.append(f"Data connections ({len(data_connections)})")

    ai_models = list(payload.get("ai_models") or [])
    if ai_models:
        areas.append(f"AI models ({len(ai_models)})")

    return areas
