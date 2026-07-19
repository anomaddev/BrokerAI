"""SQLAlchemy models for BrokerAI app schema (private to FastAPI).

Tables live in schema ``brokerai``. Nested documents (e.g. strategy params) are
stored as JSONB ``doc`` (or specific JSONB columns) so repository APIs keep
returning dicts. PostgREST roles are not granted access — see
``brokerai.db.pg.schema``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from brokerai.db.pg.base import Base

# JSONB on Postgres; portable JSON for sqlite tests.
JsonType = JSON().with_variant(JSONB(), "postgresql")


class StrategyRow(Base):
    __tablename__ = "strategies"
    __table_args__ = (
        Index("ix_strategies_asset_class_name", "asset_class", "name"),
        Index("ix_strategies_preset_id", "preset_id"),
        Index("ix_strategies_backtest_status", "backtest_status"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    asset_class: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preset_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    backtest_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="not_run", server_default="not_run"
    )
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class StrategyVersionRow(Base):
    """Point-in-time snapshot of a strategy definition after an explicit save."""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_versions_strategy_version"),
        Index("ix_strategy_versions_strategy_version", "strategy_id", "version"),
        Index("ix_strategy_versions_strategy_created", "strategy_id", "created_at"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "source", "ts", name="uq_market_candles_series_ts"
        ),
        Index("ix_market_candles_series_ts", "symbol", "timeframe", "source", "ts"),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time: Mapped[str] = mapped_column(Text, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sessions: Mapped[Any | None] = mapped_column(JsonType, nullable=True)
    trading_day_et: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CandleSyncStateRow(Base):
    __tablename__ = "candle_sync_state"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "source", name="uq_candle_sync_state"),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class CandleWatchRow(Base):
    __tablename__ = "candle_watch"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "source", "requester", name="uq_candle_watch"
        ),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    requester: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class AssetSettingsRow(Base):
    __tablename__ = "asset_settings"
    __table_args__ = {"schema": "brokerai"}

    asset_class: Mapped[str] = mapped_column(Text, primary_key=True)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class ExchangeConnectionRow(Base):
    __tablename__ = "exchange_connections"
    __table_args__ = {"schema": "brokerai"}

    exchange_id: Mapped[str] = mapped_column(Text, primary_key=True)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class DataConnectionRow(Base):
    __tablename__ = "data_connections"
    __table_args__ = (
        Index("ix_data_connections_type_model", "conn_type", "model_id"),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conn_type: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class AiModelRow(Base):
    __tablename__ = "ai_models"
    __table_args__ = {"schema": "brokerai"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class ResearchSettingsRow(Base):
    __tablename__ = "research_settings"
    __table_args__ = {"schema": "brokerai"}

    id: Mapped[str] = mapped_column(Text, primary_key=True, default="default")
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class ResearchReportReadsRow(Base):
    """Singleton JSON doc of which research reports the user has read."""

    __tablename__ = "research_report_reads"
    __table_args__ = {"schema": "brokerai"}

    id: Mapped[str] = mapped_column(Text, primary_key=True, default="default")
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class ResearchCacheRow(Base):
    __tablename__ = "research_cache"
    __table_args__ = (
        UniqueConstraint("date", "category", name="uq_research_cache_date_category"),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class AnalysisResultRow(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        Index("ix_analysis_results_symbol_created", "symbol", "created_at"),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class StrategyAnalysisRunRow(Base):
    __tablename__ = "strategy_analysis_runs"
    __table_args__ = (
        UniqueConstraint(
            "strategy_id",
            "pair",
            "candle_time",
            "analysis_purpose",
            "trade_id",
            name="uq_strategy_analysis_runs_natural",
        ),
        Index("ix_strategy_analysis_runs_analyzed_at", "analyzed_at"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    pair: Mapped[str] = mapped_column(Text, nullable=False)
    candle_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analysis_purpose: Mapped[str] = mapped_column(Text, nullable=False, default="entry")
    trade_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class BacktestRunRow(Base):
    """Queued/completed strategy backtest runs (history for the Backtest page)."""

    __tablename__ = "backtest_runs"
    __table_args__ = (
        Index("ix_backtest_runs_created_at", "created_at"),
        Index("ix_backtest_runs_strategy_id", "strategy_id"),
        Index("ix_backtest_runs_status", "status"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class BotActivityRow(Base):
    __tablename__ = "bot_activity"
    __table_args__ = (
        Index("ix_bot_activity_occurred_at", "occurred_at"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class CostLedgerRow(Base):
    __tablename__ = "cost_ledger"
    __table_args__ = (
        Index("ix_cost_ledger_occurred_at", "occurred_at"),
        Index("ix_cost_ledger_category_occurred", "category", "occurred_at"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class BrokerLotRow(Base):
    __tablename__ = "broker_lots"
    __table_args__ = (
        UniqueConstraint(
            "exchange_id", "account_id", "broker_lot_id", name="uq_broker_lots_natural"
        ),
        Index("ix_broker_lots_state", "state"),
        Index("ix_broker_lots_strategy_pair", "strategy_id", "pair"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    broker_lot_id: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    pair: Mapped[str | None] = mapped_column(Text, nullable=True)
    trade_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class BrokerEventRow(Base):
    __tablename__ = "broker_events"
    __table_args__ = (
        UniqueConstraint(
            "exchange_id",
            "account_id",
            "broker_event_id",
            name="uq_broker_events_natural",
        ),
        Index("ix_broker_events_time", "event_time"),
        Index("ix_broker_events_retention", "retention_expires_at"),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    broker_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class BrokerSyncStateRow(Base):
    __tablename__ = "broker_sync_state"
    __table_args__ = (
        UniqueConstraint("exchange_id", "account_id", name="uq_broker_sync_state"),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class InstrumentExposureRow(Base):
    __tablename__ = "instrument_exposure"
    __table_args__ = (
        UniqueConstraint(
            "exchange_id",
            "account_id",
            "symbol",
            "direction",
            name="uq_instrument_exposure",
        ),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class OandaAccountsSnapshotRow(Base):
    __tablename__ = "oanda_accounts_snapshots"
    __table_args__ = {"schema": "brokerai"}

    exchange_id: Mapped[str] = mapped_column(Text, primary_key=True)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class OandaAccountSummaryRow(Base):
    __tablename__ = "oanda_account_summaries"
    __table_args__ = (
        Index(
            "ix_oanda_account_summaries_lookup",
            "exchange_id",
            "account_id",
            "synced_at",
        ),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class ConfigBackupRow(Base):
    __tablename__ = "config_backups"
    __table_args__ = (
        Index("ix_config_backups_created_at", "created_at"),
        Index("ix_config_backups_kind_created", "kind", "created_at"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class BackupSettingsRow(Base):
    __tablename__ = "backup_settings"
    __table_args__ = {"schema": "brokerai"}

    id: Mapped[str] = mapped_column(Text, primary_key=True, default="default")
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class UserProfileRow(Base):
    """Local profile prefs linked to Supabase Auth ``sub`` (or legacy username)."""

    __tablename__ = "user_profiles"
    __table_args__ = {"schema": "brokerai"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # auth sub or local id
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    setup_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OnboardingRow(Base):
    __tablename__ = "onboarding"
    __table_args__ = {"schema": "brokerai"}

    id: Mapped[str] = mapped_column(Text, primary_key=True, default="default")
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
