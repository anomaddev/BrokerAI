"""Persist and query per-user read/unread state for research reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import ResearchReportReadsRow

LEGACY_SINGLETON_ID = "default"

# All report types count toward Daily/Weekly unread badges.
COUNTABLE_REPORT_TYPES = frozenset(
    {"daily", "daily_model", "weekly_brief", "weekly_debrief"}
)
DAILY_UNREAD_TYPES = frozenset({"daily", "daily_model"})
WEEKLY_UNREAD_TYPES = frozenset({"weekly_brief", "weekly_debrief"})


def is_countable_report_type(report_type: str | None) -> bool:
    return bool(report_type) and report_type in COUNTABLE_REPORT_TYPES


def unread_group(report_type: str | None) -> str | None:
    if report_type in DAILY_UNREAD_TYPES:
        return "daily"
    if report_type in WEEKLY_UNREAD_TYPES:
        return "weekly"
    return None


def is_unread(
    report_type: str | None,
    filename: str,
    generated_at: str | None,
    reads: dict[str, dict[str, Any]],
) -> bool:
    """Return True when a countable report has not been read at its current generation.

    Edge cases:
    - Non-countable types are never unread.
    - Missing read entry → unread.
    - Stored ``generated_at`` differing from current (including null↔value) → unread.
    - Matching ``generated_at`` (both null or equal strings) → read.
    """
    if not is_countable_report_type(report_type):
        return False
    entry = reads.get(filename)
    if entry is None:
        return True
    stored = entry.get("generated_at")
    return stored != generated_at


def _normalize_reads(doc: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    raw = (doc or {}).get("reads")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        filename = str(key).strip()
        if not filename or not isinstance(value, dict):
            continue
        read_at = value.get("read_at")
        generated_at = value.get("generated_at")
        out[filename] = {
            "read_at": str(read_at) if read_at else None,
            "generated_at": str(generated_at) if generated_at else None,
        }
    return out


def _user_id(user_id: str) -> str:
    value = (user_id or "").strip()
    if not value:
        raise ValueError("user_id is required")
    return value


class ResearchReportReadsRepository:
    COLLECTION = "research_report_reads"

    async def get_reads(self, user_id: str) -> dict[str, dict[str, Any]]:
        uid = _user_id(user_id)
        async with session_scope() as session:
            row = await session.get(ResearchReportReadsRow, uid)
            if row is None and uid != LEGACY_SINGLETON_ID:
                # One-time migrate from pre-multi-user singleton row.
                legacy = await session.get(ResearchReportReadsRow, LEGACY_SINGLETON_ID)
                if legacy is not None:
                    doc = dict(legacy.doc)
                    session.add(ResearchReportReadsRow(id=uid, doc=doc))
                    session.delete(legacy)
                    return _normalize_reads(doc)
            if row is None:
                return {}
            return _normalize_reads(dict(row.doc))

    async def mark_read(
        self, user_id: str, filename: str, generated_at: str | None
    ) -> None:
        """Idempotently record that ``filename`` was read at its current generation."""
        uid = _user_id(user_id)
        key = filename.strip()
        if not key:
            raise ValueError("filename is required")
        now = datetime.now(timezone.utc).isoformat()
        async with session_scope() as session:
            row = await session.get(ResearchReportReadsRow, uid)
            reads = _normalize_reads(dict(row.doc) if row else None)
            reads[key] = {
                "read_at": now,
                "generated_at": generated_at,
            }
            payload = {"reads": reads}
            if row is None:
                session.add(ResearchReportReadsRow(id=uid, doc=payload))
            else:
                row.doc = payload

    async def clear_read(self, user_id: str | None, filename: str) -> None:
        """Remove read state for a report.

        When ``user_id`` is None, clear the filename from every user's doc (delete).
        """
        key = filename.strip()
        if not key:
            return
        async with session_scope() as session:
            if user_id is None:
                rows = (await session.execute(select(ResearchReportReadsRow))).scalars().all()
                for row in rows:
                    reads = _normalize_reads(dict(row.doc))
                    if key in reads:
                        del reads[key]
                        row.doc = {"reads": reads}
                return
            uid = _user_id(user_id)
            row = await session.get(ResearchReportReadsRow, uid)
            if row is None:
                return
            reads = _normalize_reads(dict(row.doc))
            if key not in reads:
                return
            del reads[key]
            row.doc = {"reads": reads}

    async def mark_all_read(
        self,
        user_id: str,
        entries: list[tuple[str, str | None]],
    ) -> None:
        """Mark many ``(filename, generated_at)`` pairs as read for ``user_id``."""
        uid = _user_id(user_id)
        if not entries:
            return
        now = datetime.now(timezone.utc).isoformat()
        async with session_scope() as session:
            row = await session.get(ResearchReportReadsRow, uid)
            reads = _normalize_reads(dict(row.doc) if row else None)
            for filename, generated_at in entries:
                key = filename.strip()
                if not key:
                    continue
                reads[key] = {"read_at": now, "generated_at": generated_at}
            payload = {"reads": reads}
            if row is None:
                session.add(ResearchReportReadsRow(id=uid, doc=payload))
            else:
                row.doc = payload

