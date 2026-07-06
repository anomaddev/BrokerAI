from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from brokerai.trading.types import AnalysisResult


class FetchStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    ERROR = "error"


class WorkerState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class CandleJob:
    """One pipeline unit: symbol + timeframe + strategies at a candle close."""

    job_id: str
    asset_class: str
    symbol: str
    timeframe: str
    bar_count: int
    trigger_time: datetime
    strategies: tuple[dict, ...]
    incremental: bool = True
    bootstrap: bool = False
    catchup: bool = False

    @property
    def dedupe_key(self) -> str:
        return f"{self.symbol}|{self.timeframe}|{self.trigger_time.isoformat()}"


@dataclass
class PipelineContext:
    """Metadata handoff between Manager, Analyst, and Broker (hybrid model)."""

    job_id: str
    asset_class: str
    symbol: str
    timeframe: str
    trigger_time: datetime
    bar_count: int
    strategies: tuple[dict, ...]
    latest_candle_time: str | None = None
    fetch_status: FetchStatus = FetchStatus.SKIPPED
    candles_ref: str | None = None
    incremental: bool = True
    bootstrap: bool = False
    catchup: bool = False

    @classmethod
    def from_job(cls, job: CandleJob) -> PipelineContext:
        return cls(
            job_id=job.job_id,
            asset_class=job.asset_class,
            symbol=job.symbol,
            timeframe=job.timeframe,
            trigger_time=job.trigger_time,
            bar_count=job.bar_count,
            strategies=job.strategies,
            incremental=job.incremental,
            bootstrap=job.bootstrap,
            catchup=job.catchup,
        )


@dataclass
class PipelineRequest:
    """Input for Secretary pipeline dispatch."""

    job: CandleJob
    context: PipelineContext


@dataclass
class PipelineResult:
    """Output from a completed pipeline run."""

    job_id: str
    ok: bool
    analyses: list[AnalysisResult] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerHandle:
    """Tracks an active ephemeral worker."""

    handle_id: str
    worker_name: str
    asset_class: str
    state: WorkerState
    started_at: datetime
    job_id: str | None = None
