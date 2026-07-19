"""Idempotent Postgres schema bootstrap via SQLAlchemy ``create_all``."""

from __future__ import annotations

import logging

from sqlalchemy import text

from brokerai.db.pg.base import Base
from brokerai.db.pg.client import init_pg
from brokerai.db.pg import client as pg_client

logger = logging.getLogger(__name__)

SCHEMA = "brokerai"

# Defense-in-depth RLS on high-sensitivity tables (owner/FastAPI still bypasses).
_RLS_TABLES = (
    "strategies",
    "strategy_versions",
    "market_candles",
    "exchange_connections",
    "user_profiles",
    "onboarding",
    "broker_lots",
    "broker_events",
    "config_backups",
)

# One statement per execute — asyncpg rejects multi-command prepared statements.
_PRIVACY_STATEMENTS = (
    f"REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC",
    f"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON SCHEMA {SCHEMA} FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON SCHEMA {SCHEMA} FROM authenticated';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA {SCHEMA} TO service_role';
    EXECUTE 'GRANT ALL ON ALL TABLES IN SCHEMA {SCHEMA} TO service_role';
  END IF;
END
$$
""",
)


async def ensure_schema() -> None:
    """Create ``brokerai`` schema + tables if missing (idempotent)."""
    # Register ORM tables on Base.metadata.
    import brokerai.db.pg.models  # noqa: F401

    await init_pg()
    engine = pg_client._engine
    if engine is None:
        raise RuntimeError("Postgres engine is not initialized")

    async with engine.begin() as conn:
        dialect = conn.dialect.name
        if dialect == "postgresql":
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

        await conn.run_sync(Base.metadata.create_all)

        if dialect == "postgresql":
            # create_all does not add columns to existing tables.
            await conn.execute(
                text(
                    f"""
                    ALTER TABLE {SCHEMA}.strategies
                    ADD COLUMN IF NOT EXISTS backtest_status TEXT NOT NULL DEFAULT 'not_run'
                    """
                )
            )
            await conn.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_strategies_backtest_status
                    ON {SCHEMA}.strategies (backtest_status)
                    """
                )
            )
            for statement in _PRIVACY_STATEMENTS:
                await conn.execute(text(statement))
            for table in _RLS_TABLES:
                await conn.execute(
                    text(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")
                )

    logger.debug("Postgres schema ensure complete")
