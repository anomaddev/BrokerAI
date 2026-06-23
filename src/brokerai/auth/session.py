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

    def create_token(self, username: str) -> str:
        return self._serializer.dumps({"username": username})

    def verify_token(self, token: str) -> str | None:
        try:
            data = self._serializer.loads(
                token,
                max_age=self.settings.session_max_age,
            )
            username = data.get("username")
            return str(username) if username else None
        except (BadSignature, SignatureExpired):
            return None
