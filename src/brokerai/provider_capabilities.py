from __future__ import annotations

# Connection subtypes available per model provider type.
PROVIDER_CAPABILITIES: dict[str, list[str]] = {
    "grok": ["web_search", "x_search"],
    "open_webui": [],
    "openai": [],
    "claude": [],
}

CAPABILITY_LABELS: dict[str, str] = {
    "web_search": "Web search",
    "x_search": "X search",
}

WEB_SEARCH_CAPABILITIES = frozenset({"web_search"})
X_SEARCH_CAPABILITIES = frozenset({"x_search"})


def available_capabilities(provider_type: str) -> list[str]:
    return list(PROVIDER_CAPABILITIES.get(provider_type, []))


def capability_label(capability: str) -> str:
    return CAPABILITY_LABELS.get(capability, capability.replace("_", " ").title())


def supports_capability(provider_type: str, capability: str) -> bool:
    return capability in PROVIDER_CAPABILITIES.get(provider_type, [])
