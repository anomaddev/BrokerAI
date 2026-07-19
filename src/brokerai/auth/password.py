from __future__ import annotations

import re

import bcrypt

MIN_LENGTH = 8
MAX_LENGTH = 32


class PasswordValidationError(ValueError):
    pass


def validate_password(password: str, confirm: str) -> None:
    if password != confirm:
        raise PasswordValidationError("Passwords do not match")
    if len(password) < MIN_LENGTH or len(password) > MAX_LENGTH:
        raise PasswordValidationError(
            f"Password must be between {MIN_LENGTH} and {MAX_LENGTH} characters"
        )
    if not re.search(r"[A-Z]", password):
        raise PasswordValidationError("Password must include an uppercase letter")
    if not re.search(r"[a-z]", password):
        raise PasswordValidationError("Password must include a lowercase letter")
    if not re.search(r"[0-9]", password):
        raise PasswordValidationError("Password must include a digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise PasswordValidationError("Password must include a special character")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())
