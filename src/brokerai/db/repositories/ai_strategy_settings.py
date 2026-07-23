"""Postgres repository for AI Strategy settings (startup sequence)."""

from __future__ import annotations

from typing import Any

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import AiStrategySettingsRow
from brokerai.db.repositories.backtest_runs import BACKTEST_PERIODS, normalize_backtest_period

SINGLETON_ID = "default"

DEFAULT_STARTUP_ENABLED = True
DEFAULT_STARTUP_LOOP_COUNT = 3
DEFAULT_STARTUP_BACKTEST_PERIOD = "6m"
DEFAULT_STARTUP_TIMEOUT_MINUTES = 180

MIN_STARTUP_LOOP_COUNT = 1
MAX_STARTUP_LOOP_COUNT = 10
MIN_STARTUP_TIMEOUT_MINUTES = 15
MAX_STARTUP_TIMEOUT_MINUTES = 24 * 60


def default_ai_strategy_settings() -> dict[str, Any]:
    return {
        "startup_enabled": DEFAULT_STARTUP_ENABLED,
        "startup_loop_count": DEFAULT_STARTUP_LOOP_COUNT,
        "startup_backtest_period": DEFAULT_STARTUP_BACKTEST_PERIOD,
        "startup_timeout_minutes": DEFAULT_STARTUP_TIMEOUT_MINUTES,
    }


def _clamp_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _normalize_period(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip() in BACKTEST_PERIODS:
        return raw.strip()
    return DEFAULT_STARTUP_BACKTEST_PERIOD


def normalize_ai_strategy_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_ai_strategy_settings()
    if not raw:
        return base
    return {
        "startup_enabled": bool(raw.get("startup_enabled", DEFAULT_STARTUP_ENABLED)),
        "startup_loop_count": _clamp_int(
            raw.get("startup_loop_count", DEFAULT_STARTUP_LOOP_COUNT),
            default=DEFAULT_STARTUP_LOOP_COUNT,
            minimum=MIN_STARTUP_LOOP_COUNT,
            maximum=MAX_STARTUP_LOOP_COUNT,
        ),
        "startup_backtest_period": _normalize_period(raw.get("startup_backtest_period")),
        "startup_timeout_minutes": _clamp_int(
            raw.get("startup_timeout_minutes", DEFAULT_STARTUP_TIMEOUT_MINUTES),
            default=DEFAULT_STARTUP_TIMEOUT_MINUTES,
            minimum=MIN_STARTUP_TIMEOUT_MINUTES,
            maximum=MAX_STARTUP_TIMEOUT_MINUTES,
        ),
    }


class AiStrategySettingsRepository:
    """Singleton settings for AI Strategy startup (`brokerai.ai_strategy_settings`)."""

    COLLECTION = "ai_strategy_settings"

    async def get(self) -> dict[str, Any]:
        async with session_scope() as session:
            row = await session.get(AiStrategySettingsRow, SINGLETON_ID)
            if row is None:
                doc = default_ai_strategy_settings()
                session.add(AiStrategySettingsRow(id=SINGLETON_ID, doc=doc))
                return dict(doc)
            return normalize_ai_strategy_settings(dict(row.doc))

    async def update(
        self,
        *,
        startup_enabled: bool | None = None,
        startup_loop_count: int | None = None,
        startup_backtest_period: str | None = None,
        startup_timeout_minutes: int | None = None,
    ) -> dict[str, Any]:
        async with session_scope() as session:
            row = await session.get(AiStrategySettingsRow, SINGLETON_ID)
            current = (
                normalize_ai_strategy_settings(dict(row.doc))
                if row is not None
                else default_ai_strategy_settings()
            )
            if startup_enabled is not None:
                current["startup_enabled"] = bool(startup_enabled)
            if startup_loop_count is not None:
                current["startup_loop_count"] = _clamp_int(
                    startup_loop_count,
                    default=DEFAULT_STARTUP_LOOP_COUNT,
                    minimum=MIN_STARTUP_LOOP_COUNT,
                    maximum=MAX_STARTUP_LOOP_COUNT,
                )
            if startup_backtest_period is not None:
                current["startup_backtest_period"] = normalize_backtest_period(
                    startup_backtest_period
                )
            if startup_timeout_minutes is not None:
                current["startup_timeout_minutes"] = _clamp_int(
                    startup_timeout_minutes,
                    default=DEFAULT_STARTUP_TIMEOUT_MINUTES,
                    minimum=MIN_STARTUP_TIMEOUT_MINUTES,
                    maximum=MAX_STARTUP_TIMEOUT_MINUTES,
                )
            if row is None:
                session.add(AiStrategySettingsRow(id=SINGLETON_ID, doc=current))
            else:
                row.doc = current
            return dict(current)
