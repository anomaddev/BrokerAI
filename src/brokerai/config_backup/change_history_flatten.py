from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from brokerai.auth.general_settings import normalize_general_settings
from brokerai.db.repositories.config_backups import parse_created_at
from brokerai.market_sessions import normalize_market_indicators

CHANGE_FLATTEN_WINDOW = timedelta(minutes=5)


def normalize_payload_for_compare(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize scoped backup payloads so equivalent settings compare equal."""
    if not isinstance(payload, dict):
        return None

    normalized = deepcopy(payload)
    prefs = normalized.get("user_preferences")
    if isinstance(prefs, dict):
        general = prefs.get("general_settings")
        if isinstance(general, dict):
            prefs["general_settings"] = normalize_general_settings(
                timezone_auto=general.get("timezone_auto", True),
                timezone=general.get("timezone"),
                show_utc_times=general.get("show_utc_times", False),
                time_format=general.get("time_format", "24h"),
            )
        indicators = prefs.get("market_indicators")
        if isinstance(indicators, dict):
            prefs["market_indicators"] = normalize_market_indicators(indicators)

    return normalized


def payloads_equal(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    """Return whether two incremental backup payloads represent the same scoped state."""
    left_norm = normalize_payload_for_compare(left)
    right_norm = normalize_payload_for_compare(right)
    if left_norm is None and right_norm is None:
        return True
    if left_norm is None or right_norm is None:
        return False
    return json.dumps(left_norm, sort_keys=True, default=str) == json.dumps(
        right_norm, sort_keys=True, default=str
    )


def collect_same_trigger_streak(changes: list[dict[str, Any]], trigger: str) -> list[dict[str, Any]]:
    """Return the trailing run of *changes* (ascending) that share *trigger* with no gaps."""
    streak: list[dict[str, Any]] = []
    for change in reversed(changes):
        if str(change.get("trigger") or "") != trigger:
            break
        streak.append(change)
    streak.reverse()
    return streak


def redundant_change_ids_to_drop(
    streak: list[dict[str, Any]],
    new_payload: dict[str, Any],
) -> list[str]:
    """Return change backup ids to delete when *new_payload* completes a redundant cycle.

    Each change backup stores the scoped configuration **before** the mutation. When a user
    toggles a setting back to a snapshot that already appears earlier in the same trigger
    streak, the intermediate entries did not leave a durable configuration change and can
    be removed.

    Scan from the newest comparable slot (``len - 2``) backward so a four-toggle
    on/off/on/off sequence collapses to the first on/off pair instead of wiping the whole
    streak.
    """
    if len(streak) < 2:
        return []

    for index in range(len(streak) - 2, -1, -1):
        prior_payload = streak[index].get("payload")
        if not isinstance(prior_payload, dict):
            continue
        if not payloads_equal(new_payload, prior_payload):
            continue
        return [
            str(entry["id"])
            for entry in streak[index + 1 :]
            if entry.get("id")
        ]

    return []


def filter_changes_in_window(
    changes: list[dict[str, Any]],
    *,
    now: datetime,
    window: timedelta = CHANGE_FLATTEN_WINDOW,
) -> list[dict[str, Any]]:
    """Keep change entries whose ``created_at`` falls within *window* of *now*."""
    cutoff = now - window
    in_window: list[dict[str, Any]] = []
    for change in changes:
        created_at = parse_created_at(change.get("created_at"))
        if created_at is None or created_at < cutoff:
            continue
        in_window.append(change)
    in_window.sort(key=lambda doc: parse_created_at(doc.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc))
    return in_window


def find_redundant_change_ids(
    recent_changes: list[dict[str, Any]],
    *,
    trigger: str,
    new_payload: dict[str, Any],
    now: datetime | None = None,
    window: timedelta = CHANGE_FLATTEN_WINDOW,
) -> list[str]:
    """Return change backup ids to delete before skipping a redundant new entry, if any."""
    when = now or datetime.now(timezone.utc)
    windowed = filter_changes_in_window(recent_changes, now=when, window=window)
    streak = collect_same_trigger_streak(windowed, trigger)
    return redundant_change_ids_to_drop(streak, new_payload)


def find_redundant_change_id(
    recent_changes: list[dict[str, Any]],
    *,
    trigger: str,
    new_payload: dict[str, Any],
    now: datetime | None = None,
    window: timedelta = CHANGE_FLATTEN_WINDOW,
) -> str | None:
    """Legacy helper returning the first id slated for deletion."""
    ids = find_redundant_change_ids(
        recent_changes,
        trigger=trigger,
        new_payload=new_payload,
        now=now,
        window=window,
    )
    return ids[0] if ids else None
