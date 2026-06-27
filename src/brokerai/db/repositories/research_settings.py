from __future__ import annotations

from typing import Any

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
from brokerai.db.client import get_db

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
    return {
        "model_id": str(model_id),
        "reasoning_effort": _valid_effort(entry.get("reasoning_effort")),
        "enabled": bool(entry.get("enabled", True)),
    }


def _normalize_data_sources(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}

    def _model_id(key: str) -> str | None:
        value = raw.get(key)
        return str(value) if value else None

    return {
        "newsapi": bool(raw.get("newsapi", True)),
        "web_search_enabled": bool(raw.get("web_search_enabled", False)),
        "web_search_model_id": _model_id("web_search_model_id"),
        "x_search_enabled": bool(raw.get("x_search_enabled", False)),
        "x_search_model_id": _model_id("x_search_model_id"),
    }


def _normalize_settings(doc: dict[str, Any]) -> dict[str, Any]:
    legacy_effort = _valid_effort(doc.get("reasoning_effort"))

    contributors_raw = doc.get("contributor_models")
    if contributors_raw is None:
        ids = doc.get("selected_model_ids")
        if ids is None:
            legacy_single = doc.get("selected_model_id")
            ids = [legacy_single] if legacy_single else []
        contributors_raw = [
            {"model_id": item, "reasoning_effort": legacy_effort, "enabled": True}
            for item in ids
            if item
        ]

    contributors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for entry in contributors_raw:
        normalized = _normalize_contributor(entry)
        if normalized and normalized["model_id"] not in seen_ids:
            contributors.append(normalized)
            seen_ids.add(normalized["model_id"])

    synthesis_model_id = doc.get("synthesis_model_id")
    synthesis_model_id = str(synthesis_model_id) if synthesis_model_id else None
    synthesis_effort = _valid_effort(doc.get("synthesis_reasoning_effort", legacy_effort))

    return {
        "id": SINGLETON_ID,
        "contributor_models": contributors,
        "synthesis_model_id": synthesis_model_id,
        "synthesis_reasoning_effort": synthesis_effort,
        "data_sources": _normalize_data_sources(doc.get("data_sources")),
        "daily_report_enabled": bool(doc.get("daily_report_enabled", False)),
        "daily_report_market_id": normalize_market_id(doc.get("daily_report_market_id")),
        "daily_report_market_offset_hours": normalize_market_offset_hours(
            doc.get("daily_report_market_offset_hours")
        ),
        "last_daily_run_date": doc.get("last_daily_run_date"),
        "weekly_brief_enabled": bool(doc.get("weekly_brief_enabled", False)),
        "weekly_brief_model_id": str(doc["weekly_brief_model_id"])
        if doc.get("weekly_brief_model_id")
        else None,
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
        "weekly_debrief_model_id": str(doc["weekly_debrief_model_id"])
        if doc.get("weekly_debrief_model_id")
        else None,
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
    }


def _default_settings() -> dict[str, Any]:
    return {
        "id": SINGLETON_ID,
        "contributor_models": [],
        "synthesis_model_id": None,
        "synthesis_reasoning_effort": DAILY_REPORT_REASONING_EFFORT,
        "data_sources": _normalize_data_sources(None),
        "daily_report_enabled": False,
        "daily_report_market_id": DEFAULT_DAILY_REPORT_MARKET_ID,
        "daily_report_market_offset_hours": DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
        "last_daily_run_date": None,
        "weekly_brief_enabled": False,
        "weekly_brief_model_id": None,
        "weekly_brief_reasoning_effort": DAILY_REPORT_REASONING_EFFORT,
        "weekly_brief_market_id": DEFAULT_WEEKLY_BRIEF_MARKET_ID,
        "weekly_brief_market_offset_hours": DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS,
        "last_weekly_brief_run_week": None,
        "weekly_debrief_enabled": False,
        "weekly_debrief_model_id": None,
        "weekly_debrief_reasoning_effort": DAILY_REPORT_REASONING_EFFORT,
        "weekly_debrief_market_id": DEFAULT_WEEKLY_DEBRIEF_MARKET_ID,
        "weekly_debrief_market_offset_hours": DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS,
        "last_weekly_debrief_run_week": None,
    }


class ResearchSettingsRepository:
    COLLECTION = "research_settings"

    async def get(self) -> dict[str, Any]:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one({"id": SINGLETON_ID}, {"_id": 0})
        if doc:
            normalized = _normalize_settings(doc)
            return await self._prune_missing_models(normalized)
        return _default_settings()

    async def _prune_missing_models(self, doc: dict[str, Any]) -> dict[str, Any]:
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

        handle = await get_db()
        cursor = handle.db["ai_models"].find(
            {"id": {"$in": list(referenced)}},
            {"_id": 0, "id": 1},
        )
        docs = await cursor.to_list(length=len(referenced) + 1)
        existing = {str(doc["id"]) for doc in docs}

        missing = referenced - existing
        if not missing:
            return doc

        pruned = {
            **doc,
            "contributor_models": [
                c for c in doc["contributor_models"] if c["model_id"] in existing
            ],
            "synthesis_model_id": doc["synthesis_model_id"]
            if doc.get("synthesis_model_id") in existing
            else None,
            "weekly_brief_model_id": doc.get("weekly_brief_model_id")
            if doc.get("weekly_brief_model_id") in existing
            else None,
            "weekly_debrief_model_id": doc.get("weekly_debrief_model_id")
            if doc.get("weekly_debrief_model_id") in existing
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
        handle = await get_db()
        payload = {**doc, "id": SINGLETON_ID}
        await handle.db[self.COLLECTION].update_one(
            {"id": SINGLETON_ID},
            {
                "$set": payload,
                "$unset": {"selected_model_id": "", "selected_model_ids": "", "reasoning_effort": ""},
            },
            upsert=True,
        )

    async def save(
        self,
        *,
        contributor_models: Any = _UNSET,
        synthesis_model_id: Any = _UNSET,
        synthesis_reasoning_effort: Any = _UNSET,
        data_sources: Any = _UNSET,
        daily_report_enabled: bool | None = None,
        daily_report_market_id: str | None = None,
        daily_report_market_offset_hours: int | None = None,
        last_daily_run_date: str | None = None,
        weekly_brief_enabled: bool | None = None,
        weekly_brief_model_id: Any = _UNSET,
        weekly_brief_reasoning_effort: Any = _UNSET,
        weekly_brief_market_id: str | None = None,
        weekly_brief_market_offset_hours: int | None = None,
        last_weekly_brief_run_week: str | None = None,
        weekly_debrief_enabled: bool | None = None,
        weekly_debrief_model_id: Any = _UNSET,
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
                if item and item["model_id"] not in seen:
                    normalized.append(item)
                    seen.add(item["model_id"])
            current["contributor_models"] = normalized

        if synthesis_model_id is not _UNSET:
            current["synthesis_model_id"] = str(synthesis_model_id) if synthesis_model_id else None

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
            dict(current["data_sources"]),
        )

        current["contributor_models"] = [
            c for c in current["contributor_models"] if c["model_id"] != model_id
        ]
        if current["synthesis_model_id"] == model_id:
            current["synthesis_model_id"] = None
        if current.get("weekly_brief_model_id") == model_id:
            current["weekly_brief_model_id"] = None
        if current.get("weekly_debrief_model_id") == model_id:
            current["weekly_debrief_model_id"] = None
        sources = current["data_sources"]
        if sources.get("web_search_model_id") == model_id:
            sources["web_search_model_id"] = None
        if sources.get("x_search_model_id") == model_id:
            sources["x_search_model_id"] = None

        after = (
            [dict(c) for c in current["contributor_models"]],
            current["synthesis_model_id"],
            dict(current["data_sources"]),
        )
        if before == after:
            return False

        await self._persist(current)
        return True
