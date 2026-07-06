from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from brokerai.config.settings import Settings, get_settings


class SessionManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._serializer = URLSafeTimedSerializer(
            self.settings.secret_key,
            salt="brokerai-session",
        )

    def create_token(self, username: str, *, oidc_sub: str | None = None) -> str:
        payload: dict[str, str] = {"username": username}
        if oidc_sub:
            payload["oidc_sub"] = oidc_sub
        return self._serializer.dumps(payload)

    def verify_token(self, token: str) -> tuple[str, str | None] | None:
        try:
            data = self._serializer.loads(
                token,
                max_age=self.settings.session_max_age,
            )
            username = data.get("username")
            if not username:
                return None
            oidc_sub = data.get("oidc_sub")
            return str(username), str(oidc_sub) if oidc_sub else None
        except (BadSignature, SignatureExpired):
            return None
