"""Helpers for AI Strategy memory digests used by daily playbook backtests.

Slice 3 owns versioned digest persistence
(:class:`~brokerai.db.repositories.strategy_learning.StrategyMemoryDigestsRepository`).
Standing/anti rules are short strings; this module normalizes them for compile
and feedback apply without calling an LLM.
"""

from __future__ import annotations

import json
from typing import Any

# Keep hot-path digests bounded; newest lessons win when at capacity.
MAX_STANDING_RULES = 24
MAX_ANTI_RULES = 24
MAX_DIGEST_NOTES = 40
MAX_SUMMARY_CHARS = 400

_ALLOWED_BIAS = frozenset({"long", "short", "flat", "both"})


def empty_memory_digest(*, strategy_id: str = "", version: int | str | None = None) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "version": version if version is not None else 0,
        "standing_rules": [],
        "anti_rules": [],
        "summary": "",
        "notes": [],
        "bias": None,
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


def _normalize_bias(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    return value if value in _ALLOWED_BIAS else None


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
        "standing_rules": _normalize_rule_strings(
            raw.get("standing_rules"), limit=MAX_STANDING_RULES
        ),
        "anti_rules": _normalize_rule_strings(raw.get("anti_rules"), limit=MAX_ANTI_RULES),
        "summary": str(raw.get("summary") or "").strip(),
        "notes": _normalize_rule_strings(raw.get("notes") or [], limit=MAX_DIGEST_NOTES),
        "bias": _normalize_bias(raw.get("bias")),
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


def digest_learning_fingerprint(digest: dict[str, Any] | None) -> str:
    """Stable fingerprint of fields that affect playbook behavior and Memory UI.

    Ignores version / id / timestamps / source so a no-op rewrite is detectable
    even when metadata differs.
    """
    normalized = normalize_memory_digest(digest)
    payload = {
        "standing_rules": normalized["standing_rules"],
        "anti_rules": normalized["anti_rules"],
        "summary": normalized["summary"],
        "notes": normalized.get("notes") or [],
        "bias": normalized.get("bias"),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def digest_content_unchanged(
    prior: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> bool:
    """True when learning-relevant content is identical."""
    return digest_learning_fingerprint(prior) == digest_learning_fingerprint(candidate)


def _merge_rules_newest_first(
    new_rules: list[str],
    prior_rules: list[str],
    *,
    limit: int,
) -> list[str]:
    """Prepend new lessons; drop oldest when over capacity.

    Newest-first matters for the Memory UI preview (first N rules) and for
    recency-weighted bias inference at compile time.
    """
    out: list[str] = []
    for text in list(new_rules) + list(prior_rules):
        cleaned = str(text or "").strip()
        if not cleaned or cleaned in out:
            continue
        out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def _majority_bias(votes: list[str]) -> str | None:
    if not votes:
        return None
    counts: dict[str, int] = {}
    for vote in votes:
        key = _normalize_bias(vote)
        if key is None:
            continue
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    best = max(counts.items(), key=lambda item: item[1])
    return best[0]


def merge_feedback_notes_into_digest(
    prior: dict[str, Any] | None,
    notes: list[dict[str, Any]],
    *,
    strategy_id: str = "",
    source: str = "ai_strategy_daily_feedback",
) -> dict[str, Any]:
    """Build a new digest doc payload from prior + structured memory notes.

    Notes with ``kind`` standing_rule / anti_rule are prepended (newest first);
    other kinds go into ``notes``. Summary is rewritten to lead with *new*
    lesson text so the Memory UI visibly updates. When at capacity, oldest
    prior rules are dropped instead of silently discarding new lessons.

    Explicit ``bias`` on notes (when present) is majority-voted onto the digest
    so the next compiled playbook can change direction — rule text alone is not
    enough for the v1 bias+momentum evaluator.
    """
    out = normalize_memory_digest(prior, strategy_id=strategy_id)
    prior_standing = list(out["standing_rules"])
    prior_anti = list(out["anti_rules"])
    prior_notes = list(out.get("notes") or [])

    new_standing: list[str] = []
    new_anti: list[str] = []
    new_lessons: list[str] = []
    bias_votes: list[str] = []

    for note in notes:
        if not isinstance(note, dict):
            continue
        text = str(note.get("text") or "").strip()
        if not text:
            continue
        kind = str(note.get("kind") or "lesson").strip().lower()
        note_bias = _normalize_bias(note.get("bias"))
        if note_bias:
            bias_votes.append(note_bias)
        if kind == "standing_rule":
            if text not in new_standing and text not in prior_standing:
                new_standing.append(text)
            elif text not in new_standing:
                # Re-assert an existing rule as newest so it surfaces in UI/bias weight.
                new_standing.append(text)
        elif kind == "anti_rule":
            if text not in new_anti and text not in prior_anti:
                new_anti.append(text)
            elif text not in new_anti:
                new_anti.append(text)
        else:
            if text not in new_lessons and text not in prior_notes:
                new_lessons.append(text)
            elif text not in new_lessons:
                new_lessons.append(text)

    standing = _merge_rules_newest_first(
        new_standing, prior_standing, limit=MAX_STANDING_RULES
    )
    anti = _merge_rules_newest_first(new_anti, prior_anti, limit=MAX_ANTI_RULES)
    extra_notes = _merge_rules_newest_first(
        new_lessons, prior_notes, limit=MAX_DIGEST_NOTES
    )

    # Lead summary with *new* content so truncation keeps visible UI updates.
    # When re-applying the same notes, keep the prior summary if it already
    # starts with this lead — otherwise duplicate applies would churn text and
    # bump versions without real learning.
    summary_bits: list[str] = []
    for text in new_standing + new_anti + new_lessons:
        if text and text not in summary_bits:
            summary_bits.append(text)
    prior_summary = str(out.get("summary") or "").strip()
    if summary_bits:
        lead = " · ".join(summary_bits)
        if prior_summary == lead or prior_summary.startswith(lead):
            summary = prior_summary[:MAX_SUMMARY_CHARS].strip()
        elif prior_summary:
            summary = f"{lead} · {prior_summary}"[:MAX_SUMMARY_CHARS].strip()
        else:
            summary = lead[:MAX_SUMMARY_CHARS].strip()
    else:
        summary = prior_summary[:MAX_SUMMARY_CHARS].strip()

    voted_bias = _majority_bias(bias_votes)
    retained_bias = _normalize_bias(out.get("bias"))

    source_text = (source or "").strip() or "ai_strategy_daily_feedback"
    return {
        "standing_rules": standing,
        "anti_rules": anti,
        "summary": summary,
        "notes": extra_notes,
        "bias": voted_bias or retained_bias,
        "source": source_text,
        "covered_through": out.get("covered_through"),
    }
