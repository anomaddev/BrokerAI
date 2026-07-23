"""LLM spend gate: reserve before HTTP, settle after. ET calendar day budgets."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from brokerai.config.settings import get_settings
from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import LlmBudgetDayRow, LlmBudgetSettingsRow, LlmCallReservationRow

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
SINGLETON_ID = "default"
DEFAULT_DAILY_LIMIT_USD = 5.0
DEFAULT_UNKNOWN_MODEL_RESERVE_USD = 0.05
RESERVATION_TTL_MINUTES = 30


class LlmBudgetExceeded(RuntimeError):
    """Raised when an LLM call is denied by kill switch, budget, or in-flight conflict."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class LlmCallRequest:
    operation: str
    source: str
    provider_type: str
    model_name: str
    cache_key: str
    estimated_cost_usd: float
    cost_context: dict[str, Any]


@dataclass(frozen=True)
class LlmBudgetDecision:
    allowed: bool
    reason: str | None
    budget_day_et: str
    reservation_id: str | None
    cached_content: str | None = None


def budget_day_et(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(ET).date().isoformat()


def build_cache_key(
    *,
    operation: str,
    provider_type: str,
    model_name: str,
    entity_scope: str,
    asof_id: str,
    prompt_version: str = "v1",
    payload_hash: str = "",
) -> str:
    material = "|".join(
        [
            operation,
            provider_type,
            model_name,
            entity_scope,
            asof_id,
            prompt_version,
            payload_hash,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def default_budget_settings() -> dict[str, Any]:
    return {
        "kill_switch": False,
        "daily_limit_usd": DEFAULT_DAILY_LIMIT_USD,
        "unknown_model_reserve_usd": DEFAULT_UNKNOWN_MODEL_RESERVE_USD,
        "enabled_operations": ["*"],
    }


def normalize_budget_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_budget_settings()
    if not raw:
        return base
    try:
        daily = float(raw.get("daily_limit_usd", DEFAULT_DAILY_LIMIT_USD))
    except (TypeError, ValueError):
        daily = DEFAULT_DAILY_LIMIT_USD
    try:
        unknown = float(raw.get("unknown_model_reserve_usd", DEFAULT_UNKNOWN_MODEL_RESERVE_USD))
    except (TypeError, ValueError):
        unknown = DEFAULT_UNKNOWN_MODEL_RESERVE_USD
    enabled = raw.get("enabled_operations", ["*"])
    if not isinstance(enabled, list):
        enabled = ["*"]
    return {
        "kill_switch": bool(raw.get("kill_switch", False)),
        "daily_limit_usd": max(0.0, daily),
        "unknown_model_reserve_usd": max(0.0, unknown),
        "enabled_operations": [str(x) for x in enabled],
    }


def env_kill_switch_enabled() -> bool:
    return bool(get_settings().llm_kill_switch)


async def get_budget_settings() -> dict[str, Any]:
    async with session_scope() as session:
        row = await session.get(LlmBudgetSettingsRow, SINGLETON_ID)
        if row is None:
            doc = default_budget_settings()
            session.add(LlmBudgetSettingsRow(id=SINGLETON_ID, doc=doc))
            return dict(doc)
        return normalize_budget_settings(dict(row.doc))


async def update_budget_settings(
    *,
    kill_switch: bool | None = None,
    daily_limit_usd: float | None = None,
) -> dict[str, Any]:
    async with session_scope() as session:
        row = await session.get(LlmBudgetSettingsRow, SINGLETON_ID)
        doc = normalize_budget_settings(dict(row.doc) if row else None)
        if kill_switch is not None:
            doc["kill_switch"] = bool(kill_switch)
        if daily_limit_usd is not None:
            doc["daily_limit_usd"] = max(0.0, float(daily_limit_usd))
        if row is None:
            session.add(LlmBudgetSettingsRow(id=SINGLETON_ID, doc=doc))
        else:
            row.doc = doc
        return dict(doc)


async def should_call_llm(
    req: LlmCallRequest,
    *,
    now: datetime | None = None,
    fail_closed: bool = True,
) -> LlmBudgetDecision:
    """
    Reserve budget for an LLM call or return a deny / cache-hit decision.

    Trading-tagged operations should use ``fail_closed=True`` (default).
    """
    day = budget_day_et(now)
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    try:
        if env_kill_switch_enabled():
            return LlmBudgetDecision(False, "kill_switch", day, None)

        settings = await get_budget_settings()
        if settings.get("kill_switch"):
            return LlmBudgetDecision(False, "kill_switch", day, None)

        enabled = settings.get("enabled_operations") or ["*"]
        if "*" not in enabled and req.operation not in enabled:
            return LlmBudgetDecision(False, "operation_disabled", day, None)

        estimate = max(0.0, float(req.estimated_cost_usd))
        if estimate <= 0:
            estimate = float(settings.get("unknown_model_reserve_usd") or DEFAULT_UNKNOWN_MODEL_RESERVE_USD)

        # Drop expired holds so a crashed caller cannot block the same cache_key
        # (or inflate reserved_usd) until an unrelated reclaim job runs.
        try:
            await reclaim_expired_reservations(now=stamp)
        except Exception:
            logger.debug("Expired LLM reservation reclaim failed", exc_info=True)

        async with session_scope() as session:
            existing = (
                await session.execute(
                    select(LlmCallReservationRow).where(LlmCallReservationRow.cache_key == req.cache_key)
                )
            ).scalar_one_or_none()
            if existing is not None:
                if existing.status == "completed":
                    content = (existing.doc or {}).get("content")
                    return LlmBudgetDecision(
                        True,
                        "cache_hit",
                        day,
                        existing.id,
                        cached_content=str(content) if content is not None else None,
                    )
                if existing.status == "reserved" and existing.expires_at > stamp:
                    return LlmBudgetDecision(False, "in_flight", day, existing.id)

            # Row lock so concurrent reservations cannot oversubscribe the daily cap.
            day_row = (
                await session.execute(
                    select(LlmBudgetDayRow)
                    .where(LlmBudgetDayRow.day_et == day)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if day_row is None:
                day_row = LlmBudgetDayRow(
                    day_et=day,
                    spent_usd=0.0,
                    reserved_usd=0.0,
                    call_count=0,
                    deny_count=0,
                    updated_at=stamp,
                )
                session.add(day_row)
                await session.flush()
                day_row = (
                    await session.execute(
                        select(LlmBudgetDayRow)
                        .where(LlmBudgetDayRow.day_et == day)
                        .with_for_update()
                    )
                ).scalar_one()

            limit = float(settings.get("daily_limit_usd") or DEFAULT_DAILY_LIMIT_USD)
            projected = float(day_row.spent_usd) + float(day_row.reserved_usd) + estimate
            if projected > limit:
                day_row.deny_count = int(day_row.deny_count or 0) + 1
                day_row.updated_at = stamp
                return LlmBudgetDecision(False, "daily_cap", day, None)

            reservation_id = uuid4().hex
            expires = stamp + timedelta(minutes=RESERVATION_TTL_MINUTES)
            if existing is not None:
                existing.id = reservation_id
                existing.day_et = day
                existing.status = "reserved"
                existing.estimated_usd = estimate
                existing.actual_usd = None
                existing.operation = req.operation
                existing.created_at = stamp
                existing.settled_at = None
                existing.expires_at = expires
                existing.doc = {
                    "source": req.source,
                    "provider_type": req.provider_type,
                    "model_name": req.model_name,
                    "cost_context": dict(req.cost_context or {}),
                }
                reservation = existing
            else:
                reservation = LlmCallReservationRow(
                    id=reservation_id,
                    cache_key=req.cache_key,
                    day_et=day,
                    status="reserved",
                    estimated_usd=estimate,
                    actual_usd=None,
                    operation=req.operation,
                    created_at=stamp,
                    settled_at=None,
                    expires_at=expires,
                    doc={
                        "source": req.source,
                        "provider_type": req.provider_type,
                        "model_name": req.model_name,
                        "cost_context": dict(req.cost_context or {}),
                    },
                )
                session.add(reservation)

            day_row.reserved_usd = float(day_row.reserved_usd) + estimate
            day_row.updated_at = stamp
            return LlmBudgetDecision(True, None, day, reservation_id)
    except LlmBudgetExceeded:
        raise
    except Exception:
        logger.exception("LLM budget gate failed")
        if fail_closed:
            return LlmBudgetDecision(False, "budget_store_error", day, None)
        return LlmBudgetDecision(True, "budget_store_error_fail_open", day, None)


async def settle_llm_call(
    reservation_id: str,
    *,
    actual_cost_usd: float | None,
    content: str | None,
    ok: bool,
    now: datetime | None = None,
) -> None:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    async with session_scope() as session:
        reservation = await session.get(LlmCallReservationRow, reservation_id)
        if reservation is None:
            return
        if reservation.status in {"completed", "failed", "released"}:
            return

        day_row = await session.get(LlmBudgetDayRow, reservation.day_et)
        estimate = float(reservation.estimated_usd or 0.0)
        if day_row is not None:
            day_row.reserved_usd = max(0.0, float(day_row.reserved_usd) - estimate)
            if ok:
                actual = estimate if actual_cost_usd is None else max(0.0, float(actual_cost_usd))
                day_row.spent_usd = float(day_row.spent_usd) + actual
                day_row.call_count = int(day_row.call_count or 0) + 1
                reservation.actual_usd = actual
            day_row.updated_at = stamp

        reservation.status = "completed" if ok else "failed"
        reservation.settled_at = stamp
        doc = dict(reservation.doc or {})
        if content is not None and ok:
            # Cap stored content to avoid huge rows.
            doc["content"] = content[:50_000]
        reservation.doc = doc


async def reclaim_expired_reservations(*, now: datetime | None = None) -> int:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    reclaimed = 0
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(LlmCallReservationRow).where(
                    LlmCallReservationRow.status == "reserved",
                    LlmCallReservationRow.expires_at <= stamp,
                )
            )
        ).scalars().all()
        for reservation in rows:
            day_row = await session.get(LlmBudgetDayRow, reservation.day_et)
            if day_row is not None:
                day_row.reserved_usd = max(
                    0.0, float(day_row.reserved_usd) - float(reservation.estimated_usd or 0.0)
                )
                day_row.updated_at = stamp
            reservation.status = "released"
            reservation.settled_at = stamp
            reclaimed += 1
    return reclaimed
