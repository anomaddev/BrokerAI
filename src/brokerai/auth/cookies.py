from __future__ import annotations

from fastapi import Request, Response

from brokerai.config.settings import Settings, get_settings


def session_cookie_secure(request: Request | None, settings: Settings | None = None) -> bool:
    """Return whether the session cookie should include the Secure attribute.

    When ``session_cookie_secure`` is unset in settings, the cookie is marked Secure
    only when the request arrived over HTTPS (via ``X-Forwarded-Proto``).
    """
    settings = settings or get_settings()
    if settings.session_cookie_secure is not None:
        return settings.session_cookie_secure
    if request is None:
        return False
    forwarded = request.headers.get("x-forwarded-proto", "").lower()
    return forwarded == "https"


def set_session_cookie(response: Response, token: str, request: Request | None = None) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=session_cookie_secure(request, settings),
        max_age=settings.session_max_age,
        path="/",
    )


def delete_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
