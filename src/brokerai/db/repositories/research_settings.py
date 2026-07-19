from __future__ import annotations

from typing import Any

from sqlalchemy import select

from brokerai.bots.researcher.rss_feeds import normalize_rss_categories
from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import AiModelRow, ResearchSettingsRow
from brokerai.research_constants import DAILY_REPORT_REASONING_EFFORT, REASONING_EFFORT_OPTIONS
from brokerai.research_markets import (
    DEFAULT_DAILY_REPORT_MARKET_ID,
    DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
    DEFAULT_WEEKLY_BRIEF_MARKET_ID,
    DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS,
    DEFAULT_WEEKLY_DEBRIEF_MARKET_ID,
    DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS,
    normalize_market_id,
    normalize_market_offset_hours,
)

SINGLETON_ID = "default"

_UNSET = object()


def _valid_effort(value: Any) -> str:
    return value if value in REASONING_EFFORT_OPTIONS else DAILY_REPORT_REASONING_EFFORT


def _normalize_contributor(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    model_id = entry.get("model_id")
    if not model_id:
        return None
    model_name = entry.get("model_name")
    model_name = str(model_name).strip() if model_name else None
    return {
        "model_id": str(model_id),
        "model_name": model_name or None,
        "reasoning_effort": _valid_effort(entry.get("reasoning_effort")),
        "enabled": bool(entry.get("enabled", True)),
    }


def _contributor_key(entry: dict[str, Any]) -> str:
    return f"{entry.get('model_id')}\0{entry.get('model_name') or ''}"


def _normalize_data_sources(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}

    def _model_id(key: str) -> str | None:
        value = raw.get(key)
        return str(value) if value else None

    return {
        "newsapi": bool(raw.get("newsapi", True)),
        "rss_enabled": bool(raw.get("rss_enabled", False)),
        "rss_categories": normalize_rss_categories(raw.get("rss_categories")),
        "web_search_enabled": bool(raw.get("web_search_enabled", False)),
        "web_search_model_id": _model_id("web_search_model_id"),
        "x_search_enabled": bool(raw.get("x_search_enabled", False)),
        "x_search_model_id": _model_id("x_search_model_id"),
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_settings(doc: dict[str, Any]) -> dict[str, Any]:
    contributors_raw = doc.get("contributor_models") or []

    contributors: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for entry in contributors_raw:
        normalized = _normalize_contributor(entry)
        if not normalized:
            continue
        key = _contributor_key(normalized)
        if key in seen_keys:
            continue
        contributors.append(normalized)
        seen_keys.add(key)

    synthesis_model_id = _optional_str(doc.get("synthesis_model_id"))
    synthesis_effort = _valid_effort(doc.get("synthesis_reasoning_effort"))

    return {
        "id": SINGLETON_ID,
        "contributor_models": contributors,
        "synthesis_model_id": synthesis_model_id,
        "synthesis_model_name": _optional_str(doc.get("synthesis_model_name")),
        "synthesis_reasoning_effort": synthesis_effort,
        "data_sources": _normalize_data_sources(doc.get("data_sources")),
        "daily_report_enabled": bool(doc.get("daily_report_enabled", False)),
        "daily_report_market_id": normalize_market_id(doc.get("daily_report_market_id")),
        "daily_report_market_offset_hours": normalize_market_offset_hours(
            doc.get("daily_report_market_offset_hours")
        ),
        "last_daily_run_date": doc.get("last_daily_run_date"),
        "weekly_brief_enabled": bool(doc.get("weekly_brief_enabled", False)),
        "weekly_brief_model_id": _optional_str(doc.get("weekly_brief_model_id")),
        "weekly_brief_model_name": _optional_str(doc.get("weekly_brief_model_name")),
        "weekly_brief_reasoning_effort": _valid_effort(
            doc.get("weekly_brief_reasoning_effort", DAILY_REPORT_REASONING_EFFORT)
        ),
        "weekly_brief_market_id": normalize_market_id(
            doc.get("weekly_brief_market_id") or DEFAULT_WEEKLY_BRIEF_MARKET_ID
        ),
        "weekly_brief_market_offset_hours": normalize_market_offset_hours(
            doc.get("weekly_brief_market_offset_hours", DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS)
        ),
        "last_weekly_brief_run_week": doc.get("last_weekly_brief_run_week"),
        "weekly_debrief_enabled": bool(doc.get("weekly_debrief_enabled", False)),
        "weekly_debrief_model_id": _optional_str(doc.get("weekly_debrief_model_id")),
        "weekly_debrief_model_name": _optional_str(doc.get("weekly_debrief_model_name")),
        "weekly_debrief_reasoning_effort": _valid_effort(
            doc.get("weekly_debrief_reasoning_effort", DAILY_REPORT_REASONING_EFFORT)
        ),
        "weekly_debrief_market_id": normalize_market_id(
            doc.get("weekly_debrief_market_id") or DEFAULT_WEEKLY_DEBRIEF_MARKET_ID
        ),
        "weekly_debrief_market_offset_hours": normalize_market_offset_hours(
            doc.get("weekly_debrief_market_offset_hours", DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS)
        ),
        "last_weekly_debrief_run_week": doc.get("last_weekly_debrief_run_week"),
        "unread_digest_enabled": bool(doc.get("unread_digest_enabled", False)),
    }


def _default_settings() -> dict[str, Any]:
    return {
        "id": SINGLETON_ID,
        "contributor_models": [],
        "synthesis_model_id": None,
        "synthesis_model_name": None,
        "synthesis_reasoning_effort": DAILY_REPORT_REASONING_EFFORT,
        "data_sources": _normalize_data_sources(None),
        "daily_report_enabled": False,
        "daily_report_market_id": DEFAULT_DAILY_REPORT_MARKET_ID,
        "daily_report_market_offset_hours": DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
        "last_daily_run_date": None,
        "weekly_brief_enabled": False,
        "weekly_brief_model_id": None,
        "weekly_brief_model_name": None,
        "weekly_brief_reasoning_effort": DAILY_REPORT_REASONING_EFFORT,
        "weekly_brief_market_id": DEFAULT_WEEKLY_BRIEF_MARKET_ID,
        "weekly_brief_market_offset_hours": DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS,
        "last_weekly_brief_run_week": None,
        "weekly_debrief_enabled": False,
        "weekly_debrief_model_id": None,
        "weekly_debrief_model_name": None,
        "weekly_debrief_reasoning_effort": DAILY_REPORT_REASONING_EFFORT,
        "weekly_debrief_market_id": DEFAULT_WEEKLY_DEBRIEF_MARKET_ID,
        "weekly_debrief_market_offset_hours": DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS,
        "last_weekly_debrief_run_week": None,
        "unread_digest_enabled": False,
    }


class ResearchSettingsRepository:
    COLLECTION = "research_settings"

    async def get(self) -> dict[str, Any]:
        async with session_scope() as session:
            row = await session.get(ResearchSettingsRow, SINGLETON_ID)
            if row:
                normalized = _normalize_settings(dict(row.doc))
                pruned = await self._prune_missing_models(normalized, session)
                return await self._backfill_model_names(pruned, session)
        return _default_settings()

    async def _load_models_by_id(
        self,
        model_ids: set[str],
        session=None,
    ) -> dict[str, dict[str, Any]]:
        if not model_ids:
            return {}

        async def _load(sess) -> dict[str, dict[str, Any]]:
            stmt = select(AiModelRow).where(AiModelRow.id.in_(list(model_ids)))
            rows = (await sess.execute(stmt)).scalars().all()
            return {str(row.id): dict(row.doc) for row in rows}

        if session is not None:
            return await _load(session)
        async with session_scope() as scoped:
            return await _load(scoped)

    async def _backfill_model_names(
        self,
        doc: dict[str, Any],
        session=None,
    ) -> dict[str, Any]:
        """Fill missing selection model_name fields from the API source defaults."""
        referenced: set[str] = {c["model_id"] for c in doc.get("contributor_models", [])}
        for key in (
            "synthesis_model_id",
            "weekly_brief_model_id",
            "weekly_debrief_model_id",
        ):
            if doc.get(key):
                referenced.add(str(doc[key]))

        models_by_id = await self._load_models_by_id(referenced, session)
        if not models_by_id:
            return doc

        def _fallback(source_id: str | None) -> str | None:
            if not source_id:
                return None
            source = models_by_id.get(source_id)
            if not source:
                return None
            for key in ("default_model_name", "model_name"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return None

        changed = False
        contributors: list[dict[str, Any]] = []
        for entry in doc.get("contributor_models", []):
            item = dict(entry)
            if not item.get("model_name"):
                filled = _fallback(item.get("model_id"))
                if filled:
                    item["model_name"] = filled
                    changed = True
            contributors.append(item)

        updated = {**doc, "contributor_models": contributors}
        for id_key, name_key in (
            ("synthesis_model_id", "synthesis_model_name"),
            ("weekly_brief_model_id", "weekly_brief_model_name"),
            ("weekly_debrief_model_id", "weekly_debrief_model_name"),
        ):
            if updated.get(id_key) and not updated.get(name_key):
                filled = _fallback(updated.get(id_key))
                if filled:
                    updated[name_key] = filled
                    changed = True

        if changed:
            await self._persist(updated)
        return updated

    async def _prune_missing_models(
        self,
        doc: dict[str, Any],
        session=None,
    ) -> dict[str, Any]:
        referenced: set[str] = {c["model_id"] for c in doc.get("contributor_models", [])}
        for key in (
            "synthesis_model_id",
            "weekly_brief_model_id",
            "weekly_debrief_model_id",
        ):
            if doc.get(key):
                referenced.add(doc[key])
        sources = doc.get("data_sources", {})
        for key in ("web_search_model_id", "x_search_model_id"):
            if sources.get(key):
                referenced.add(sources[key])

        if not referenced:
            return doc

        models_by_id = await self._load_models_by_id(referenced, session)
        existing = set(models_by_id)

        missing = referenced - existing
        if not missing:
            return doc

        synthesis_id = doc.get("synthesis_model_id")
        brief_id = doc.get("weekly_brief_model_id")
        debrief_id = doc.get("weekly_debrief_model_id")
        pruned = {
            **doc,
            "contributor_models": [
                c for c in doc["contributor_models"] if c["model_id"] in existing
            ],
            "synthesis_model_id": synthesis_id if synthesis_id in existing else None,
            "synthesis_model_name": doc.get("synthesis_model_name")
            if synthesis_id in existing
            else None,
            "weekly_brief_model_id": brief_id if brief_id in existing else None,
            "weekly_brief_model_name": doc.get("weekly_brief_model_name")
            if brief_id in existing
            else None,
            "weekly_debrief_model_id": debrief_id if debrief_id in existing else None,
            "weekly_debrief_model_name": doc.get("weekly_debrief_model_name")
            if debrief_id in existing
            else None,
            "data_sources": {
                **sources,
                "web_search_model_id": sources.get("web_search_model_id")
                if sources.get("web_search_model_id") in existing
                else None,
                "x_search_model_id": sources.get("x_search_model_id")
                if sources.get("x_search_model_id") in existing
                else None,
            },
        }
        await self._persist(pruned)
        return pruned

    async def _persist(self, doc: dict[str, Any]) -> None:
        payload = {**doc, "id": SINGLETON_ID}
        async with session_scope() as session:
            row = await session.get(ResearchSettingsRow, SINGLETON_ID)
            if row is None:
                session.add(ResearchSettingsRow(id=SINGLETON_ID, doc=payload))
            else:
                row.doc = payload

    async def save(
        self,
        *,
        contributor_models: Any = _UNSET,
        synthesis_model_id: Any = _UNSET,
        synthesis_model_name: Any = _UNSET,
        synthesis_reasoning_effort: Any = _UNSET,
        data_sources: Any = _UNSET,
        daily_report_enabled: bool | None = None,
        daily_report_market_id: str | None = None,
        daily_report_market_offset_hours: int | None = None,
        last_daily_run_date: str | None = None,
        weekly_brief_enabled: bool | None = None,
        weekly_brief_model_id: Any = _UNSET,
        weekly_brief_model_name: Any = _UNSET,
        weekly_brief_reasoning_effort: Any = _UNSET,
        weekly_brief_market_id: str | None = None,
        weekly_brief_market_offset_hours: int | None = None,
        last_weekly_brief_run_week: str | None = None,
        weekly_debrief_enabled: bool | None = None,
        weekly_debrief_model_id: Any = _UNSET,
        weekly_debrief_model_name: Any = _UNSET,
        weekly_debrief_reasoning_effort: Any = _UNSET,
        weekly_debrief_market_id: str | None = None,
        weekly_debrief_market_offset_hours: int | None = None,
        last_weekly_debrief_run_week: str | None = None,
    ) -> dict[str, Any]:
        current = await self.get()

        if contributor_models is not _UNSET:
            normalized: list[dict[str, Any]] = []
            seen: set[str] = set()
            for entry in contributor_models or []:
                item = _normalize_contributor(entry)
                if not item:
                    continue
                key = _contributor_key(item)
                if key in seen:
                    continue
                normalized.append(item)
                seen.add(key)
            current["contributor_models"] = normalized

        if synthesis_model_id is not _UNSET:
            current["synthesis_model_id"] = str(synthesis_model_id) if synthesis_model_id else None
            if not current["synthesis_model_id"]:
                current["synthesis_model_name"] = None
        if synthesis_model_name is not _UNSET:
            current["synthesis_model_name"] = _optional_str(synthesis_model_name)

        if synthesis_reasoning_effort is not _UNSET and synthesis_reasoning_effort is not None:
            if synthesis_reasoning_effort not in REASONING_EFFORT_OPTIONS:
                raise ValueError(f"Invalid reasoning_effort: {synthesis_reasoning_effort}")
            current["synthesis_reasoning_effort"] = synthesis_reasoning_effort

        if data_sources is not _UNSET and data_sources is not None:
            current["data_sources"] = _normalize_data_sources(data_sources)

        if daily_report_enabled is not None:
            current["daily_report_enabled"] = daily_report_enabled
        if daily_report_market_id is not None:
            current["daily_report_market_id"] = normalize_market_id(daily_report_market_id)
        if daily_report_market_offset_hours is not None:
            current["daily_report_market_offset_hours"] = normalize_market_offset_hours(
                daily_report_market_offset_hours
            )
        if last_daily_run_date is not None:
            current["last_daily_run_date"] = last_daily_run_date

        if weekly_brief_enabled is not None:
            current["weekly_brief_enabled"] = weekly_brief_enabled
        if weekly_brief_model_id is not _UNSET:
            current["weekly_brief_model_id"] = (
                str(weekly_brief_model_id) if weekly_brief_model_id else None
            )
            if not current["weekly_brief_model_id"]:
                current["weekly_brief_model_name"] = None
        if weekly_brief_model_name is not _UNSET:
            current["weekly_brief_model_name"] = _optional_str(weekly_brief_model_name)
        if weekly_brief_reasoning_effort is not _UNSET and weekly_brief_reasoning_effort is not None:
            if weekly_brief_reasoning_effort not in REASONING_EFFORT_OPTIONS:
                raise ValueError(f"Invalid reasoning_effort: {weekly_brief_reasoning_effort}")
            current["weekly_brief_reasoning_effort"] = weekly_brief_reasoning_effort
        if weekly_brief_market_id is not None:
            current["weekly_brief_market_id"] = normalize_market_id(weekly_brief_market_id)
        if weekly_brief_market_offset_hours is not None:
            current["weekly_brief_market_offset_hours"] = normalize_market_offset_hours(
                weekly_brief_market_offset_hours
            )
        if last_weekly_brief_run_week is not None:
            current["last_weekly_brief_run_week"] = last_weekly_brief_run_week

        if weekly_debrief_enabled is not None:
            current["weekly_debrief_enabled"] = weekly_debrief_enabled
        if weekly_debrief_model_id is not _UNSET:
            current["weekly_debrief_model_id"] = (
                str(weekly_debrief_model_id) if weekly_debrief_model_id else None
            )
            if not current["weekly_debrief_model_id"]:
                current["weekly_debrief_model_name"] = None
        if weekly_debrief_model_name is not _UNSET:
            current["weekly_debrief_model_name"] = _optional_str(weekly_debrief_model_name)
        if weekly_debrief_reasoning_effort is not _UNSET and weekly_debrief_reasoning_effort is not None:
            if weekly_debrief_reasoning_effort not in REASONING_EFFORT_OPTIONS:
                raise ValueError(f"Invalid reasoning_effort: {weekly_debrief_reasoning_effort}")
            current["weekly_debrief_reasoning_effort"] = weekly_debrief_reasoning_effort
        if weekly_debrief_market_id is not None:
            current["weekly_debrief_market_id"] = normalize_market_id(weekly_debrief_market_id)
        if weekly_debrief_market_offset_hours is not None:
            current["weekly_debrief_market_offset_hours"] = normalize_market_offset_hours(
                weekly_debrief_market_offset_hours
            )
        if last_weekly_debrief_run_week is not None:
            current["last_weekly_debrief_run_week"] = last_weekly_debrief_run_week

        await self._persist(current)
        return _normalize_settings(current)

    async def set_last_daily_run_date(self, date_str: str) -> dict[str, Any]:
        return await self.save(last_daily_run_date=date_str)

    async def clear_last_daily_run_date(self) -> dict[str, Any]:
        current = await self.get()
        current["last_daily_run_date"] = None
        await self._persist(current)
        return _normalize_settings(current)

    async def set_last_weekly_brief_run_week(self, week_key: str) -> dict[str, Any]:
        return await self.save(last_weekly_brief_run_week=week_key)

    async def set_last_weekly_debrief_run_week(self, week_key: str) -> dict[str, Any]:
        return await self.save(last_weekly_debrief_run_week=week_key)

    async def remove_model_references(self, model_id: str) -> bool:
        """Drop a deleted model from contributors, synthesis, and data sources."""
        current = await self.get()
        before = (
            [dict(c) for c in current["contributor_models"]],
            current["synthesis_model_id"],
            current.get("synthesis_model_name"),
            current.get("weekly_brief_model_id"),
            current.get("weekly_brief_model_name"),
            current.get("weekly_debrief_model_id"),
            current.get("weekly_debrief_model_name"),
            dict(current["data_sources"]),
        )

        current["contributor_models"] = [
            c for c in current["contributor_models"] if c["model_id"] != model_id
        ]
        if current["synthesis_model_id"] == model_id:
            current["synthesis_model_id"] = None
            current["synthesis_model_name"] = None
        if current.get("weekly_brief_model_id") == model_id:
            current["weekly_brief_model_id"] = None
            current["weekly_brief_model_name"] = None
        if current.get("weekly_debrief_model_id") == model_id:
            current["weekly_debrief_model_id"] = None
            current["weekly_debrief_model_name"] = None
        sources = current["data_sources"]
        if sources.get("web_search_model_id") == model_id:
            sources["web_search_model_id"] = None
        if sources.get("x_search_model_id") == model_id:
            sources["x_search_model_id"] = None

        after = (
            [dict(c) for c in current["contributor_models"]],
            current["synthesis_model_id"],
            current.get("synthesis_model_name"),
            current.get("weekly_brief_model_id"),
            current.get("weekly_brief_model_name"),
            current.get("weekly_debrief_model_id"),
            current.get("weekly_debrief_model_name"),
            dict(current["data_sources"]),
        )
        if before == after:
            return False

        await self._persist(current)
        return True

    async def remap_model_references(self, from_id: str, to_id: str) -> bool:
        """Rewrite research settings that pointed at from_id to to_id."""
        if from_id == to_id:
            return False
        current = await self.get()
        changed = False

        remapped_contributors: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in current["contributor_models"]:
            item = dict(entry)
            if item.get("model_id") == from_id:
                item["model_id"] = to_id
                changed = True
            key = _contributor_key(item)
            if key in seen:
                changed = True
                continue
            remapped_contributors.append(item)
            seen.add(key)
        current["contributor_models"] = remapped_contributors

        for id_key in (
            "synthesis_model_id",
            "weekly_brief_model_id",
            "weekly_debrief_model_id",
        ):
            if current.get(id_key) == from_id:
                current[id_key] = to_id
                changed = True

        sources = current["data_sources"]
        for key in ("web_search_model_id", "x_search_model_id"):
            if sources.get(key) == from_id:
                sources[key] = to_id
                changed = True

        if not changed:
            return False
        await self._persist(current)
        return True
