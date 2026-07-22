"""Postgres repository for backtest processor settings."""

from __future__ import annotations

from typing import Any

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BacktestSettingsRow
from brokerai.db.repositories.backtest_runs import BACKTEST_PERIODS, normalize_backtest_period
from brokerai.research_constants import REASONING_EFFORT_OPTIONS

SINGLETON_ID = "default"

DEFAULT_MAX_CONCURRENT = 2
DEFAULT_AUTO_START = True
DEFAULT_AI_FEEDBACK_ENABLED = False
DEFAULT_AI_FEEDBACK_AUTO_ON_COMPLETE = False
DEFAULT_AI_FEEDBACK_REASONING_EFFORT = "medium"
DEFAULT_DAILY_AI_STRATEGY_BACKTEST_ENABLED = False
DEFAULT_DAILY_AI_STRATEGY_BACKTEST_PERIOD = "6m"
MIN_CONCURRENT = 1
MAX_CONCURRENT = 10


def default_backtest_settings() -> dict[str, Any]:
    return {
        "max_concurrent": DEFAULT_MAX_CONCURRENT,
        "auto_start": DEFAULT_AUTO_START,
        "ai_feedback_enabled": DEFAULT_AI_FEEDBACK_ENABLED,
        "ai_feedback_auto_on_complete": DEFAULT_AI_FEEDBACK_AUTO_ON_COMPLETE,
        "ai_feedback_model_id": None,
        "ai_feedback_model_name": None,
        "ai_feedback_reasoning_effort": DEFAULT_AI_FEEDBACK_REASONING_EFFORT,
        "daily_ai_strategy_backtest_enabled": DEFAULT_DAILY_AI_STRATEGY_BACKTEST_ENABLED,
        "daily_ai_strategy_backtest_period": DEFAULT_DAILY_AI_STRATEGY_BACKTEST_PERIOD,
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_reasoning_effort(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip() in REASONING_EFFORT_OPTIONS:
        return raw.strip()
    return DEFAULT_AI_FEEDBACK_REASONING_EFFORT


def _normalize_daily_period(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip() in BACKTEST_PERIODS:
        return raw.strip()
    return DEFAULT_DAILY_AI_STRATEGY_BACKTEST_PERIOD


def normalize_backtest_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_backtest_settings()
    if not raw:
        return base
    try:
        max_concurrent = int(raw.get("max_concurrent", DEFAULT_MAX_CONCURRENT))
    except (TypeError, ValueError):
        max_concurrent = DEFAULT_MAX_CONCURRENT
    max_concurrent = max(MIN_CONCURRENT, min(MAX_CONCURRENT, max_concurrent))
    return {
        "max_concurrent": max_concurrent,
        "auto_start": bool(raw.get("auto_start", DEFAULT_AUTO_START)),
        "ai_feedback_enabled": bool(
            raw.get("ai_feedback_enabled", DEFAULT_AI_FEEDBACK_ENABLED)
        ),
        "ai_feedback_auto_on_complete": bool(
            raw.get("ai_feedback_auto_on_complete", DEFAULT_AI_FEEDBACK_AUTO_ON_COMPLETE)
        ),
        "ai_feedback_model_id": _optional_str(raw.get("ai_feedback_model_id")),
        "ai_feedback_model_name": _optional_str(raw.get("ai_feedback_model_name")),
        "ai_feedback_reasoning_effort": _normalize_reasoning_effort(
            raw.get("ai_feedback_reasoning_effort")
        ),
        "daily_ai_strategy_backtest_enabled": bool(
            raw.get(
                "daily_ai_strategy_backtest_enabled",
                DEFAULT_DAILY_AI_STRATEGY_BACKTEST_ENABLED,
            )
        ),
        "daily_ai_strategy_backtest_period": _normalize_daily_period(
            raw.get("daily_ai_strategy_backtest_period")
        ),
    }


class BacktestSettingsRepository:
    """Singleton settings for the backtest coordinator (`brokerai.backtest_settings`)."""

    COLLECTION = "backtest_settings"

    async def get(self) -> dict[str, Any]:
        async with session_scope() as session:
            row = await session.get(BacktestSettingsRow, SINGLETON_ID)
            if row is None:
                doc = default_backtest_settings()
                session.add(BacktestSettingsRow(id=SINGLETON_ID, doc=doc))
                return dict(doc)
            return normalize_backtest_settings(dict(row.doc))

    async def update(
        self,
        *,
        max_concurrent: int | None = None,
        auto_start: bool | None = None,
        ai_feedback_enabled: bool | None = None,
        ai_feedback_auto_on_complete: bool | None = None,
        ai_feedback_model_id: Any = None,
        ai_feedback_model_name: Any = None,
        ai_feedback_reasoning_effort: str | None = None,
        clear_ai_feedback_model: bool = False,
        daily_ai_strategy_backtest_enabled: bool | None = None,
        daily_ai_strategy_backtest_period: str | None = None,
    ) -> dict[str, Any]:
        async with session_scope() as session:
            row = await session.get(BacktestSettingsRow, SINGLETON_ID)
            current = (
                normalize_backtest_settings(dict(row.doc))
                if row is not None
                else default_backtest_settings()
            )
            if max_concurrent is not None:
                current["max_concurrent"] = max(
                    MIN_CONCURRENT, min(MAX_CONCURRENT, int(max_concurrent))
                )
            if auto_start is not None:
                current["auto_start"] = bool(auto_start)
            if ai_feedback_enabled is not None:
                current["ai_feedback_enabled"] = bool(ai_feedback_enabled)
            if ai_feedback_auto_on_complete is not None:
                current["ai_feedback_auto_on_complete"] = bool(ai_feedback_auto_on_complete)
            if clear_ai_feedback_model:
                current["ai_feedback_model_id"] = None
                current["ai_feedback_model_name"] = None
            else:
                if ai_feedback_model_id is not None:
                    current["ai_feedback_model_id"] = _optional_str(ai_feedback_model_id)
                if ai_feedback_model_name is not None:
                    current["ai_feedback_model_name"] = _optional_str(ai_feedback_model_name)
            if ai_feedback_reasoning_effort is not None:
                current["ai_feedback_reasoning_effort"] = _normalize_reasoning_effort(
                    ai_feedback_reasoning_effort
                )
            if daily_ai_strategy_backtest_enabled is not None:
                current["daily_ai_strategy_backtest_enabled"] = bool(
                    daily_ai_strategy_backtest_enabled
                )
            if daily_ai_strategy_backtest_period is not None:
                current["daily_ai_strategy_backtest_period"] = normalize_backtest_period(
                    daily_ai_strategy_backtest_period
                )
            if row is None:
                session.add(BacktestSettingsRow(id=SINGLETON_ID, doc=current))
            else:
                row.doc = current
            return dict(current)
