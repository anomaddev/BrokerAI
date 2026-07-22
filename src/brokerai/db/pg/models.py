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
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    current_bar: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class BacktestLogRow(Base):
    """Buffered log lines emitted while a backtest worker runs."""

    __tablename__ = "backtest_logs"
    __table_args__ = (
        Index("ix_backtest_logs_run_created", "run_id", "created_at"),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BacktestActionRow(Base):
    """Meaningful backtest events for step-through review (not every bar)."""

    __tablename__ = "backtest_actions"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "sequence", name="uq_backtest_actions_run_sequence"
        ),
        Index("ix_backtest_actions_run_bar", "run_id", "bar_time"),
        {"schema": "brokerai"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    bar_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BacktestSettingsRow(Base):
    """Singleton backtest processor settings (max concurrent, auto-start)."""

    __tablename__ = "backtest_settings"
    __table_args__ = {"schema": "brokerai"}

    id: Mapped[str] = mapped_column(Text, primary_key=True, default="default")
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
    # Public Supabase Storage download URL when avatars are stored remotely.
    profile_photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OnboardingRow(Base):
    __tablename__ = "onboarding"
    __table_args__ = {"schema": "brokerai"}

    id: Mapped[str] = mapped_column(Text, primary_key=True, default="default")
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class ShadowIntentRow(Base):
    """Hypothetical trade intent during AI Strategy warm-up (not sent to broker)."""

    __tablename__ = "shadow_intents"
    __table_args__ = (
        Index("ix_shadow_intents_strategy_pair", "strategy_id", "pair"),
        Index("ix_shadow_intents_created", "created_at"),
        UniqueConstraint(
            "strategy_id",
            "pair",
            "entry_candle_open",
            "direction",
            name="uq_shadow_intents_natural",
        ),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    pair: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False, default="")
    analysis_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    phase: Mapped[str] = mapped_column(Text, nullable=False, default="warming")
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    entry_candle_open: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class ShadowLotRow(Base):
    """Shadow position ledger isolated from broker_lots / OANDA reconcile."""

    __tablename__ = "shadow_lots"
    __table_args__ = (
        Index("ix_shadow_lots_strategy_state", "strategy_id", "state"),
        Index("ix_shadow_lots_pair_state", "pair", "state"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    pair: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    shadow_intent_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class TradeOutcomeRecordRow(Base):
    """Append-only shadow/live trade outcomes for learning (Slice 1 writes shadow)."""

    __tablename__ = "trade_outcome_records"
    __table_args__ = (
        Index("ix_trade_outcomes_strategy_exit", "strategy_id", "exit_ts"),
        Index("ix_trade_outcomes_mode", "mode"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)  # shadow | live
    pair: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False, default="")
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    entry_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class StrategyMemoryDigestRow(Base):
    """Versioned compact memory digest for AI Strategy (standing/anti rules)."""

    __tablename__ = "strategy_memory_digests"
    __table_args__ = (
        UniqueConstraint(
            "strategy_id",
            "version",
            name="uq_strategy_memory_digests_strategy_version",
        ),
        Index(
            "ix_strategy_memory_digests_strategy_version",
            "strategy_id",
            "version",
        ),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class LearningJobRow(Base):
    """Batched outcome-learning jobs (never per-close LLM)."""

    __tablename__ = "learning_jobs"
    __table_args__ = (
        Index("ix_learning_jobs_strategy_status", "strategy_id", "status"),
        Index("ix_learning_jobs_status_created", "status", "created_at"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class AiStrategySettingsRow(Base):
    """Singleton AI Strategy settings (startup sequence knobs)."""

    __tablename__ = "ai_strategy_settings"
    __table_args__ = {"schema": "brokerai"}

    id: Mapped[str] = mapped_column(Text, primary_key=True, default="default")
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class AiStrategyStartupJobRow(Base):
    """Durable create-time AI Strategy startup workflow (reports → seed → loops)."""

    __tablename__ = "ai_strategy_startup_jobs"
    __table_args__ = (
        Index("ix_ai_startup_jobs_strategy_status", "strategy_id", "status"),
        Index("ix_ai_startup_jobs_status_created", "status", "created_at"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    phase: Mapped[str] = mapped_column(Text, nullable=False, default="ensuring_reports")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class StrategyGuidanceRow(Base):
    """Structured research bias for AI Strategy (hot path; no markdown)."""

    __tablename__ = "strategy_guidance"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_key",
            "symbol",
            name="uq_strategy_guidance_source_symbol",
        ),
        Index("ix_strategy_guidance_symbol_as_of", "symbol", "as_of_date"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False, default="")
    as_of_date: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ok")
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class LlmBudgetSettingsRow(Base):
    """Singleton LLM spend controls."""

    __tablename__ = "llm_budget_settings"
    __table_args__ = {"schema": "brokerai"}

    id: Mapped[str] = mapped_column(Text, primary_key=True, default="default")
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class LlmBudgetDayRow(Base):
    """ET calendar-day spend / reserved totals."""

    __tablename__ = "llm_budget_days"
    __table_args__ = {"schema": "brokerai"}

    day_et: Mapped[str] = mapped_column(Text, primary_key=True)
    spent_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reserved_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deny_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LlmCallReservationRow(Base):
    """Idempotent LLM call reservation / cache."""

    __tablename__ = "llm_call_reservations"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_llm_call_reservations_cache_key"),
        Index("ix_llm_call_reservations_day_status", "day_et", "status"),
        {"schema": "brokerai"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)
    day_et: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="reserved")
    estimated_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    actual_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    operation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
