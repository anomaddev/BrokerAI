from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from brokerai.config.settings import Settings, get_settings

USERS_FILE = "users.json"


@dataclass
class UserRecord:
    username: str
    password_hash: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> UserRecord:
        return cls(
            username=data["username"],
            password_hash=data["password_hash"],
            created_at=data["created_at"],
        )


def is_valid_username(username: str) -> bool:
    return _valid_username(username)


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

    def create_user(self, username: str, password_hash: str) -> UserRecord:
        if self.is_setup_complete():
            raise ValueError("Setup already complete")
        if not _valid_username(username):
            raise ValueError("Invalid username")
        self.ensure_dir()
        record = UserRecord(
            username=username,
            password_hash=password_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.users_path.write_text(json.dumps(record.to_dict(), indent=2))
        (self.auth_dir / "setup_complete").touch()
        return record


def _valid_username(username: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", username))
