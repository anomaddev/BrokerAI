"""Default connection settings for AI API sources."""

from __future__ import annotations

PROVIDER_TYPES = ("open_webui", "openai", "claude", "grok")

DEFAULT_BASE_URLS: dict[str, str] = {
    "open_webui": "http://10.0.2.2",
    "openai": "https://api.openai.com/v1",
    "claude": "https://api.anthropic.com/v1",
    "grok": "https://api.x.ai/v1",
}

DEFAULT_TITLES: dict[str, str] = {
    "open_webui": "Open WebUI",
    "openai": "OpenAI",
    "claude": "Claude",
    "grok": "Grok",
}

# Providers that hide base URL in the UI and always use the default.
FIXED_BASE_URL_TYPES = frozenset({"openai", "claude", "grok"})


def default_base_url(provider_type: str) -> str:
    return DEFAULT_BASE_URLS.get(provider_type, "")


def default_title(provider_type: str) -> str:
    return DEFAULT_TITLES.get(provider_type, provider_type)


def resolve_base_url(provider_type: str, base_url: str | None) -> str:
    """Return a usable base URL, falling back to the provider default."""
    cleaned = (base_url or "").strip().rstrip("/")
    if cleaned:
        return cleaned
    return default_base_url(provider_type).rstrip("/")
