from __future__ import annotations

from brokerai.config.settings import Settings, get_settings

AuthMode = str


def auth_mode(settings: Settings | None = None) -> AuthMode:
    settings = settings or get_settings()
    return settings.auth_mode


def is_builtin_mode(settings: Settings | None = None) -> bool:
    return auth_mode(settings) == "builtin"


def is_oidc_mode(settings: Settings | None = None) -> bool:
    return auth_mode(settings) == "oidc"
