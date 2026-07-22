"""Helpers for AI Strategy memory digests used by daily playbook backtests.

Slice 3 owns versioned digest persistence
(:class:`~brokerai.db.repositories.strategy_learning.StrategyMemoryDigestsRepository`).
Standing/anti rules are short strings; this module normalizes them for compile
and feedback apply without calling an LLM.
"""

from __future__ import annotations

from typing import Any


def empty_memory_digest(*, strategy_id: str = "", version: int | str | None = None) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "version": version if version is not None else 0,
        "standing_rules": [],
        "anti_rules": [],
        "summary": "",
        "notes": [],
    }


def _normalize_rule_strings(raw: Any, *, limit: int = 24) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = str(item or "").strip()
        if not text:
            continue
        if text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def normalize_memory_digest(raw: dict[str, Any] | None, *, strategy_id: str = "") -> dict[str, Any]:
    """Sanitize a Slice-3 digest document for compile/feedback use."""
    base = empty_memory_digest(strategy_id=strategy_id)
    if not isinstance(raw, dict):
        return base
    sid = str(raw.get("strategy_id") or strategy_id or "").strip()
    version = raw.get("version", 0)
    try:
        version_out: int | str = int(version)
    except (TypeError, ValueError):
        version_out = str(version or "").strip() or 0
    return {
        "id": raw.get("id"),
        "strategy_id": sid,
        "version": version_out,
        "standing_rules": _normalize_rule_strings(raw.get("standing_rules")),
        "anti_rules": _normalize_rule_strings(raw.get("anti_rules")),
        "summary": str(raw.get("summary") or "").strip(),
        "notes": _normalize_rule_strings(raw.get("notes") or [], limit=40),
        "covered_through": raw.get("covered_through"),
        "created_at": raw.get("created_at"),
    }


def digest_is_queueable(digest: dict[str, Any] | None) -> bool:
    """True when a digest has at least one standing or anti rule to compile."""
    if not digest:
        return False
    normalized = normalize_memory_digest(digest)
    return bool(normalized["standing_rules"] or normalized["anti_rules"])


def digest_version_key(digest: dict[str, Any] | None) -> str:
    """Stable string form of digest version for run metadata / skip checks."""
    if not digest:
        return ""
    version = digest.get("version")
    if version is None or version == "" or version == 0:
        return ""
    return str(version)


def merge_feedback_notes_into_digest(
    prior: dict[str, Any] | None,
    notes: list[dict[str, Any]],
    *,
    strategy_id: str = "",
) -> dict[str, Any]:
    """Build a new digest doc payload from prior + structured memory notes.

    Notes with ``kind`` standing_rule / anti_rule are appended to those lists;
    other kinds go into ``notes`` / extend ``summary``.
    """
    out = normalize_memory_digest(prior, strategy_id=strategy_id)
    standing = list(out["standing_rules"])
    anti = list(out["anti_rules"])
    extra_notes = list(out.get("notes") or [])
    summary_bits: list[str] = []
    if out.get("summary"):
        summary_bits.append(str(out["summary"]))

    for note in notes:
        if not isinstance(note, dict):
            continue
        text = str(note.get("text") or "").strip()
        if not text:
            continue
        kind = str(note.get("kind") or "lesson").strip().lower()
        if kind == "standing_rule":
            if text not in standing:
                standing.append(text)
        elif kind == "anti_rule":
            if text not in anti:
                anti.append(text)
        else:
            if text not in extra_notes:
                extra_notes.append(text)
            summary_bits.append(text)

    return {
        "standing_rules": standing[:24],
        "anti_rules": anti[:24],
        "summary": " ".join(summary_bits)[:400].strip(),
        "notes": extra_notes[:40],
        "source": "ai_strategy_daily_feedback",
        "covered_through": out.get("covered_through"),
    }
