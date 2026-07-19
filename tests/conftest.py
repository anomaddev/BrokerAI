"""Shared pytest fixtures for BrokerAI tests."""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from brokerai.config.settings import reload_settings


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_dumps(value: object) -> str:
    return json.dumps(value, default=_json_default)


@pytest.fixture(autouse=True)
def _file_auth_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth/onboarding tests use file-backed AuthStore unless overridden.

    Clear Supabase Auth env so setup/login do not hit a live GoTrue from ``.env``.
    """
    monkeypatch.setenv("BROKERAI_USE_POSTGRES", "false")
    monkeypatch.setenv("BROKERAI_SUPABASE_URL", "")
    monkeypatch.setenv("BROKERAI_SUPABASE_ANON_KEY", "")
    monkeypatch.setenv("BROKERAI_SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.setenv("BROKERAI_SUPABASE_JWT_SECRET", "")
    reload_settings()


@pytest.fixture
async def sqlite_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Async SQLite engine with BrokerAI ORM tables for repository tests."""
    import brokerai.db.pg.client as pg_client
    from brokerai.db.pg.base import Base

    db_path = tmp_path / "brokerai-test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("BROKERAI_DATABASE_URL", url)
    reload_settings()
    await pg_client.close_pg()

    saved_schemas = {name: table.schema for name, table in Base.metadata.tables.items()}
    for table in Base.metadata.tables.values():
        table.schema = None

    # SQLite only autoincrements INTEGER PRIMARY KEY; coerce bigint id columns.
    from sqlalchemy import Integer

    for table in Base.metadata.tables.values():
        if table.name in {"broker_events", "market_candles"} and "id" in table.c:
            table.c.id.type = Integer()
            table.c.id.autoincrement = True

    engine = create_async_engine(
        url,
        json_serializer=_json_dumps,
        json_deserializer=json.loads,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragma(dbapi_conn, _connection_record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    pg_client._engine = engine
    pg_client._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    yield pg_client._session_factory

    await pg_client.close_pg()
    for name, table in Base.metadata.tables.items():
        table.schema = saved_schemas[name]
    reload_settings()
