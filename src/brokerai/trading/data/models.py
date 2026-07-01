from __future__ import annotations

from pydantic import BaseModel, Field


class SyncResult(BaseModel):
    symbol: str
    timeframe: str
    upserted: int = 0
    complete: bool = False
    error: str | None = None


class BackfillResult(BaseModel):
    symbol: str
    timeframe: str
    upserted: int = 0
    chunks: int = 0
    error: str | None = None


class VerifyResult(BaseModel):
    symbol: str
    timeframe: str
    missing_count: int = 0
    missing_times: list[str] = Field(default_factory=list)
    complete: bool = False


class CacheStatus(BaseModel):
    symbol: str
    timeframe: str
    count: int
    latest_time: str | None
    complete: bool
