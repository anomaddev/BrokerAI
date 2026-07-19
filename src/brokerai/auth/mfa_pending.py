"""Short-lived signed tokens for MFA login / enroll handoffs.

BrokerAI sessions are cookie-based; Supabase access tokens are only needed during
the MFA challenge or enrollment window. These tokens bridge that gap without
persisting GoTrue JWTs in the browser.
"""

from __future__ import annotations

from typing import Any, Literal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from brokerai.config.settings import Settings, get_settings

MfaPurpose = Literal["login", "enroll"]

# Match GoTrue's default MFA challenge lifetime.
MFA_PENDING_MAX_AGE = 300


class MfaPendingManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._serializer = URLSafeTimedSerializer(
            self.settings.secret_key,
            salt="brokerai-mfa-pending",
        )

    def create(
        self,
        *,
        username: str,
        access_token: str,
        purpose: MfaPurpose,
        factor_id: str | None = None,
        oidc_sub: str | None = None,
    ) -> str:
        payload: dict[str, str] = {
            "username": username,
            "access_token": access_token,
            "purpose": purpose,
        }
        if factor_id:
            payload["factor_id"] = factor_id
        if oidc_sub:
            payload["oidc_sub"] = oidc_sub
        return self._serializer.dumps(payload)

    def verify(self, token: str, *, purpose: MfaPurpose | None = None) -> dict[str, Any] | None:
        try:
            data = self._serializer.loads(token, max_age=MFA_PENDING_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return None
        username = data.get("username")
        access_token = data.get("access_token")
        token_purpose = data.get("purpose")
        if not username or not access_token or token_purpose not in ("login", "enroll"):
            return None
        if purpose is not None and token_purpose != purpose:
            return None
        return {
            "username": str(username),
            "access_token": str(access_token),
            "purpose": str(token_purpose),
            "factor_id": str(data["factor_id"]) if data.get("factor_id") else None,
            "oidc_sub": str(data["oidc_sub"]) if data.get("oidc_sub") else None,
        }
