from __future__ import annotations

from typing import Any

from brokerai.db.repositories.asset_settings import ASSET_CLASSES

# Top-level payload keys that may appear in incremental snapshots.
PAYLOAD_SECTIONS = frozenset(
    {
        "user_preferences",
        "system_settings",
        "asset_settings",
        "strategies",
        "exchange_connections",
        "research_settings",
        "data_connections",
        "ai_models",
    }
)


def _asset_class_from_trigger(trigger: str) -> str | None:
    if not trigger.startswith("asset_settings."):
        return None
    asset_class = trigger.split(".", 1)[-1]
    return asset_class if asset_class in ASSET_CLASSES else None


def sections_for_trigger(trigger: str) -> frozenset[str]:
    """Return top-level payload section keys affected by a settings mutation trigger."""
    if trigger.startswith("account.general"):
        return frozenset({"user_preferences"})
    if trigger.startswith("account.display"):
        return frozenset({"user_preferences"})
    if trigger.startswith("settings.update"):
        return frozenset({"system_settings"})
    if trigger.startswith("asset_settings."):
        return frozenset({"asset_settings"})
    if trigger.startswith("strategies."):
        return frozenset({"strategies"})
    if trigger.startswith("exchange_connections."):
        return frozenset({"exchange_connections"})
    if trigger.startswith("data_connections."):
        return frozenset({"data_connections"})
    if trigger.startswith("ai_models."):
        return frozenset({"ai_models"})
    if trigger.startswith("research_settings"):
        return frozenset({"research_settings"})
    if trigger in {"manual", "baseline", "restore", "schedule", "import"}:
        return PAYLOAD_SECTIONS
    return PAYLOAD_SECTIONS


def extract_scoped_sections(payload: dict[str, Any], trigger: str) -> dict[str, Any]:
    """Slice a full snapshot to only the sections relevant to *trigger*."""
    sections = sections_for_trigger(trigger)
    scoped: dict[str, Any] = {"schema_version": payload.get("schema_version", 2)}

    if "user_preferences" in sections:
        prefs = payload.get("user_preferences")
        if isinstance(prefs, dict):
            if trigger.startswith("account.general"):
                general = prefs.get("general_settings")
                if general is not None:
                    scoped["user_preferences"] = {"general_settings": general}
            elif trigger.startswith("account.display"):
                indicators = prefs.get("market_indicators")
                if indicators is not None:
                    scoped["user_preferences"] = {"market_indicators": indicators}
            else:
                scoped["user_preferences"] = dict(prefs)

    if "system_settings" in sections:
        system = payload.get("system_settings")
        if isinstance(system, dict) and system:
            scoped["system_settings"] = dict(system)

    if "asset_settings" in sections:
        asset_class = _asset_class_from_trigger(trigger)
        all_assets = list(payload.get("asset_settings") or [])
        if asset_class:
            scoped["asset_settings"] = [
                doc for doc in all_assets if doc.get("asset_class") == asset_class
            ]
        elif all_assets:
            scoped["asset_settings"] = list(all_assets)

    for key in ("strategies", "exchange_connections", "data_connections", "ai_models"):
        if key in sections:
            value = payload.get(key)
            if isinstance(value, list) and value:
                scoped[key] = list(value)

    if "research_settings" in sections:
        research = payload.get("research_settings")
        if isinstance(research, dict) and research:
            scoped["research_settings"] = dict(research)

    return scoped


def merge_payload_sections(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *overlay* sections into *base*, replacing list collections wholesale."""
    merged = dict(base)

    overlay_prefs = overlay.get("user_preferences")
    if isinstance(overlay_prefs, dict):
        base_prefs = dict(merged.get("user_preferences") or {})
        if "general_settings" in overlay_prefs:
            base_prefs["general_settings"] = overlay_prefs["general_settings"]
        if "market_indicators" in overlay_prefs:
            base_prefs["market_indicators"] = overlay_prefs["market_indicators"]
        merged["user_preferences"] = base_prefs

    if isinstance(overlay.get("system_settings"), dict):
        merged["system_settings"] = dict(overlay["system_settings"])

    overlay_assets = overlay.get("asset_settings")
    if isinstance(overlay_assets, list):
        base_assets = list(merged.get("asset_settings") or [])
        by_class = {doc.get("asset_class"): doc for doc in base_assets if doc.get("asset_class")}
        for doc in overlay_assets:
            asset_class = doc.get("asset_class")
            if asset_class:
                by_class[asset_class] = doc
        merged["asset_settings"] = list(by_class.values())

    for key in ("strategies", "exchange_connections", "data_connections", "ai_models"):
        if key in overlay and isinstance(overlay[key], list):
            merged[key] = list(overlay[key])

    if isinstance(overlay.get("research_settings"), dict):
        merged["research_settings"] = dict(overlay["research_settings"])

    if "schema_version" in overlay:
        merged["schema_version"] = overlay["schema_version"]

    return merged
