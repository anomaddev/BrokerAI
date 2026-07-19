"""Authentication for BrokerAI web UI."""

from brokerai.auth.password import (
    PasswordValidationError,
    hash_password,
    validate_password,
    verify_password,
)
from brokerai.auth.session import SessionManager
from brokerai.auth.store import (
    AuthStore,
    UserRecord,
    is_valid_email,
    is_valid_username,
    normalize_optional_name,
    username_from_email,
)

__all__ = [
    "AuthStore",
    "PasswordValidationError",
    "SessionManager",
    "UserRecord",
    "hash_password",
    "is_valid_email",
    "is_valid_username",
    "normalize_optional_name",
    "username_from_email",
    "validate_password",
    "verify_password",
]
