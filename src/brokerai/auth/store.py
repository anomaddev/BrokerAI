from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from brokerai.config.settings import Settings, get_settings
from brokerai.auth.general_settings import normalize_general_settings, resolved_general_settings
from brokerai.market_sessions import normalize_market_indicators

USERS_FILE = "users.json"
MAX_NAME_LENGTH = 64


@dataclass
class UserRecord:
    username: str
    password_hash: str | None
    created_at: str
    oidc_sub: str | None = None
    profile_photo: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    market_indicators: dict[str, bool] | None = None
    timezone_auto: bool | None = None
    timezone: str | None = None
    show_utc_times: bool | None = None
    time_format: str | None = None

    def replace(self, **changes: object) -> UserRecord:
        return UserRecord(
            username=str(changes["username"]) if "username" in changes else self.username,
            password_hash=changes["password_hash"] if "password_hash" in changes else self.password_hash,  # type: ignore[assignment]
            created_at=str(changes["created_at"]) if "created_at" in changes else self.created_at,
            oidc_sub=changes["oidc_sub"] if "oidc_sub" in changes else self.oidc_sub,  # type: ignore[assignment]
            profile_photo=changes["profile_photo"] if "profile_photo" in changes else self.profile_photo,  # type: ignore[assignment]
            first_name=changes["first_name"] if "first_name" in changes else self.first_name,  # type: ignore[assignment]
            last_name=changes["last_name"] if "last_name" in changes else self.last_name,  # type: ignore[assignment]
            market_indicators=changes["market_indicators"] if "market_indicators" in changes else self.market_indicators,  # type: ignore[assignment]
            timezone_auto=changes["timezone_auto"] if "timezone_auto" in changes else self.timezone_auto,  # type: ignore[assignment]
            timezone=changes["timezone"] if "timezone" in changes else self.timezone,  # type: ignore[assignment]
            show_utc_times=changes["show_utc_times"] if "show_utc_times" in changes else self.show_utc_times,  # type: ignore[assignment]
            time_format=changes["time_format"] if "time_format" in changes else self.time_format,  # type: ignore[assignment]
        )

    def resolved_market_indicators(self) -> dict[str, bool]:
        return normalize_market_indicators(self.market_indicators)

    def resolved_general_settings(self) -> dict[str, bool | str | None]:
        return resolved_general_settings(
            {
                "timezone_auto": self.timezone_auto,
                "timezone": self.timezone,
                "show_utc_times": self.show_utc_times,
                "time_format": self.time_format,
            }
        )

    def to_dict(self) -> dict[str, object]:
        general = self.resolved_general_settings()
        payload: dict[str, object] = {
            "username": self.username,
            "created_at": self.created_at,
            "market_indicators": self.resolved_market_indicators(),
            "timezone_auto": general["timezone_auto"],
            "timezone": general["timezone"],
            "show_utc_times": general["show_utc_times"],
            "time_format": general["time_format"],
        }
        if self.password_hash:
            payload["password_hash"] = self.password_hash
        if self.oidc_sub:
            payload["oidc_sub"] = self.oidc_sub
        if self.profile_photo:
            payload["profile_photo"] = self.profile_photo
        if self.first_name:
            payload["first_name"] = self.first_name
        if self.last_name:
            payload["last_name"] = self.last_name
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> UserRecord:
        profile_photo = data.get("profile_photo") or None
        first_name = data.get("first_name") or None
        last_name = data.get("last_name") or None
        password_hash = data.get("password_hash")
        oidc_sub = data.get("oidc_sub")
        return cls(
            username=str(data["username"]),
            password_hash=str(password_hash) if password_hash else None,
            created_at=str(data["created_at"]),
            oidc_sub=str(oidc_sub) if oidc_sub else None,
            profile_photo=str(profile_photo) if profile_photo else None,
            first_name=str(first_name) if first_name else None,
            last_name=str(last_name) if last_name else None,
            market_indicators=normalize_market_indicators(data.get("market_indicators")),
            timezone_auto=data.get("timezone_auto") if "timezone_auto" in data else None,
            timezone=str(data["timezone"]) if data.get("timezone") else None,
            show_utc_times=data.get("show_utc_times") if "show_utc_times" in data else None,
            time_format=str(data["time_format"]) if data.get("time_format") else None,
        )


def is_valid_username(username: str) -> bool:
    return _valid_username(username)


def normalize_optional_name(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = " ".join(value.split())
    if not trimmed:
        return None
    if len(trimmed) > MAX_NAME_LENGTH:
        raise ValueError(f"Name must be {MAX_NAME_LENGTH} characters or fewer")
    return trimmed


class AuthStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.auth_dir = self.settings.auth_dir
        self.users_path = self.auth_dir / USERS_FILE

    def ensure_dir(self) -> None:
        self.auth_dir.mkdir(parents=True, exist_ok=True)

    def is_setup_complete(self) -> bool:
        if not self.users_path.exists():
            return False
        try:
            data = json.loads(self.users_path.read_text())
            return bool(data.get("username"))
        except (json.JSONDecodeError, OSError):
            return False

    def get_user(self) -> UserRecord | None:
        if not self.users_path.exists():
            return None
        try:
            return UserRecord.from_dict(json.loads(self.users_path.read_text()))
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def _save_user(self, record: UserRecord) -> UserRecord:
        self.users_path.write_text(json.dumps(record.to_dict(), indent=2))
        return record

    def create_user(
        self,
        username: str,
        password_hash: str,
        profile_photo: str | None = None,
    ) -> UserRecord:
        if self.is_setup_complete():
            raise ValueError("Setup already complete")
        if not _valid_username(username):
            raise ValueError("Invalid username")
        self.ensure_dir()
        record = UserRecord(
            username=username,
            password_hash=password_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
            profile_photo=profile_photo,
        )
        self._save_user(record)
        (self.auth_dir / "setup_complete").touch()
        return record

    def create_or_link_oidc_user(
        self,
        *,
        oidc_sub: str,
        username: str,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> UserRecord:
        """Create the local profile on first OIDC login or link an existing profile."""
        allowed = self.settings.oidc_allowed_sub.strip()
        if allowed and oidc_sub != allowed:
            raise ValueError("OIDC subject is not allowed for this BrokerAI instance")

        existing = self.get_user()
        if existing is not None:
            if existing.oidc_sub and existing.oidc_sub != oidc_sub:
                raise ValueError("OIDC subject does not match the linked BrokerAI profile")
            record = existing.replace(
                oidc_sub=oidc_sub,
                first_name=first_name if first_name is not None else existing.first_name,
                last_name=last_name if last_name is not None else existing.last_name,
            )
            self._save_user(record)
            (self.auth_dir / "setup_complete").touch()
            return record

        if not _valid_username(username):
            raise ValueError("Invalid username derived from OIDC claims")
        self.ensure_dir()
        record = UserRecord(
            username=username,
            password_hash=None,
            oidc_sub=oidc_sub,
            created_at=datetime.now(timezone.utc).isoformat(),
            first_name=first_name,
            last_name=last_name,
        )
        self._save_user(record)
        (self.auth_dir / "setup_complete").touch()
        return record

    def set_profile_photo(self, filename: str | None) -> UserRecord:
        user = self.get_user()
        if user is None:
            raise ValueError("No user")
        return self._save_user(user.replace(profile_photo=filename))

    def update_username(self, new_username: str) -> UserRecord:
        user = self.get_user()
        if user is None:
            raise ValueError("No user")
        if not _valid_username(new_username):
            raise ValueError("Invalid username")
        return self._save_user(user.replace(username=new_username))

    def update_password(self, password_hash: str) -> UserRecord:
        user = self.get_user()
        if user is None:
            raise ValueError("No user")
        return self._save_user(user.replace(password_hash=password_hash))

    def update_profile(self, first_name: str | None, last_name: str | None) -> UserRecord:
        user = self.get_user()
        if user is None:
            raise ValueError("No user")
        return self._save_user(user.replace(first_name=first_name, last_name=last_name))

    def update_market_indicators(self, market_indicators: dict[str, bool]) -> UserRecord:
        user = self.get_user()
        if user is None:
            raise ValueError("No user")
        normalized = normalize_market_indicators(market_indicators)
        return self._save_user(user.replace(market_indicators=normalized))

    def update_general_settings(
        self,
        *,
        timezone_auto: bool,
        timezone: str | None,
        show_utc_times: bool,
        time_format: str,
    ) -> UserRecord:
        user = self.get_user()
        if user is None:
            raise ValueError("No user")
        normalized = normalize_general_settings(
            timezone_auto=timezone_auto,
            timezone=timezone,
            show_utc_times=show_utc_times,
            time_format=time_format,
        )
        return self._save_user(
            user.replace(
                timezone_auto=bool(normalized["timezone_auto"]),
                timezone=str(normalized["timezone"]) if normalized["timezone"] else None,
                show_utc_times=bool(normalized["show_utc_times"]),
                time_format=str(normalized["time_format"]),
            )
        )


def _valid_username(username: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", username))
