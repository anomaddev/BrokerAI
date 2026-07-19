"""Async SQLAlchemy engine and session helpers for Postgres."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _json_default(value: object) -> str:
    """Serialize datetime/date values stored inside JSONB document columns."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_dumps(value: object) -> str:
    return json.dumps(value, default=_json_default)


def _database_url() -> str:
    settings = get_settings()
    url = (settings.database_url or "").strip()
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def init_pg() -> async_sessionmaker[AsyncSession]:
    """Create the global async engine/session factory (idempotent)."""
    global _engine, _session_factory
    if _session_factory is not None:
        return _session_factory
    url = _database_url()
    _engine = create_async_engine(
        url,
        pool_pre_ping=True,
        json_serializer=_json_dumps,
        json_deserializer=json.loads,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncSession:
    """Return a new ``AsyncSession`` (caller must close or use ``session_scope``)."""
    factory = await init_pg()
    return factory()


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Commit on success, rollback on error, always close."""
    session = await get_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def ping_pg() -> bool:
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.debug("Postgres ping failed", exc_info=True)
        return False


async def close_pg() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
