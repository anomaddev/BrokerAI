"""Synchronous Postgres profile/onboarding helpers for AuthStore (SQLAlchemy sync)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from brokerai.config.settings import get_settings
from brokerai.db.pg.models import OnboardingRow, UserProfileRow

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _sync_url() -> str:
    url = get_settings().database_url.strip()
    if "+asyncpg" in url:
        # Prefer psycopg3 driver for sync AuthStore access.
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    return url


def _get_factory() -> sessionmaker[Session]:
    global _engine, _SessionLocal
    if _SessionLocal is not None:
        return _SessionLocal
    _engine = create_engine(_sync_url(), pool_pre_ping=True)
    _SessionLocal = sessionmaker(_engine, expire_on_commit=False)
    return _SessionLocal


def reset_pg_profile_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def _profile_photo_url_from_doc(doc: dict[str, Any]) -> str | None:
    """Return a remote download URL from the profile doc, if present."""
    value = doc.get("profile_photo")
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if trimmed.lower().startswith("http://") or trimmed.lower().startswith("https://"):
        return trimmed
    return None


def load_user_profile() -> dict[str, Any] | None:
    factory = _get_factory()
    with factory() as session:
        row = session.scalar(select(UserProfileRow).limit(1))
        if row is None:
            return None
        doc = dict(row.doc)
        doc["username"] = row.username
        doc["_profile_id"] = row.id
        doc["_setup_complete"] = row.setup_complete
        # Prefer the first-class column when set (Supabase Storage download URL).
        if row.profile_photo_url:
            doc["profile_photo"] = row.profile_photo_url
        return doc


def save_user_profile(
    *,
    profile_id: str,
    username: str,
    setup_complete: bool,
    doc: dict[str, Any],
) -> None:
    factory = _get_factory()
    with factory() as session:
        row = session.get(UserProfileRow, profile_id)
        payload = {k: v for k, v in doc.items() if not str(k).startswith("_")}
        photo_url = _profile_photo_url_from_doc(payload)
        if row is None:
            # Single-tenant: replace any existing profile row.
            for existing in session.scalars(select(UserProfileRow)).all():
                session.delete(existing)
            session.add(
                UserProfileRow(
                    id=profile_id,
                    username=username,
                    setup_complete=setup_complete,
                    doc=payload,
                    profile_photo_url=photo_url,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        else:
            row.username = username
            row.setup_complete = setup_complete
            row.doc = payload
            row.profile_photo_url = photo_url
            row.updated_at = datetime.now(timezone.utc)
        session.commit()


def is_setup_complete_pg() -> bool:
    factory = _get_factory()
    with factory() as session:
        row = session.scalar(select(UserProfileRow).limit(1))
        return bool(row and row.setup_complete and row.username)


def load_onboarding() -> dict[str, Any] | None:
    factory = _get_factory()
    with factory() as session:
        row = session.get(OnboardingRow, "default")
        return dict(row.doc) if row else None


def save_onboarding(doc: dict[str, Any]) -> None:
    factory = _get_factory()
    with factory() as session:
        row = session.get(OnboardingRow, "default")
        if row is None:
            session.add(OnboardingRow(id="default", doc=doc))
        else:
            row.doc = doc
        session.commit()


def delete_onboarding() -> None:
    factory = _get_factory()
    with factory() as session:
        row = session.get(OnboardingRow, "default")
        if row is not None:
            session.delete(row)
            session.commit()
