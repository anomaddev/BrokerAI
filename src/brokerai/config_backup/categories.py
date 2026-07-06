from __future__ import annotations

_ASSET_CLASS_PAGES: dict[str, str] = {
    "forex": "Forex",
    "metals": "Precious Metals",
    "stocks": "Stocks",
    "crypto": "Crypto",
    "futures": "Futures",
    "options": "Options",
}


def category_for_trigger(trigger: str) -> str:
    """Map a backup trigger to the settings page name where the change originated."""
    if trigger.startswith("account.general"):
        return "General"
    if trigger.startswith("account.display"):
        return "Display"
    if trigger.startswith("account."):
        return "Account"
    if trigger.startswith("settings.update"):
        return "System"
    if trigger.startswith("asset_settings."):
        asset_class = trigger.split(".", 1)[-1]
        return _ASSET_CLASS_PAGES.get(asset_class, asset_class.replace("_", " ").title())
    if trigger.startswith("strategies."):
        return "Strategies"
    if trigger.startswith("exchange_connections."):
        return "Connections"
    if trigger.startswith("data_connections."):
        return "Connections"
    if trigger.startswith("ai_models."):
        return "Models"
    if trigger.startswith("research_settings.rss"):
        return "Data"
    if trigger.startswith("research_settings"):
        return "Reports"
    if trigger in {"manual", "baseline", "restore", "schedule", "import", "backup.schedule"}:
        return "Backup"
    return "Settings"
