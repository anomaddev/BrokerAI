from __future__ import annotations

from datetime import datetime, timedelta, timezone

from brokerai.config_backup.change_history_flatten import (
    CHANGE_FLATTEN_WINDOW,
    collect_same_trigger_streak,
    find_redundant_change_id,
    find_redundant_change_ids,
    normalize_payload_for_compare,
    payloads_equal,
    redundant_change_ids_to_drop,
)


def _change(
    *,
    change_id: str,
    trigger: str,
    payload: dict,
    minutes_ago: float,
) -> dict:
    created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {
        "id": change_id,
        "trigger": trigger,
        "payload": payload,
        "created_at": created_at.isoformat(),
    }


def _general_payload(*, show_utc: bool, time_format: str = "24h") -> dict:
    return {
        "schema_version": 2,
        "user_preferences": {
            "general_settings": {
                "timezone_auto": True,
                "timezone": "America/New_York",
                "show_utc_times": show_utc,
                "time_format": time_format,
            }
        },
    }


def test_payloads_equal_normalizes_general_settings():
    left = _general_payload(show_utc=False, time_format="bogus")
    right = _general_payload(show_utc=False, time_format="24h")
    assert payloads_equal(left, right)


def test_payloads_equal_compares_scoped_snapshots():
    left = _general_payload(show_utc=False)
    right = _general_payload(show_utc=False)
    other = _general_payload(show_utc=True)
    assert payloads_equal(left, right)
    assert not payloads_equal(left, other)


def test_normalize_payload_for_compare_is_idempotent():
    payload = _general_payload(show_utc=True)
    once = normalize_payload_for_compare(payload)
    twice = normalize_payload_for_compare(once or {})
    assert once == twice


def test_collect_same_trigger_streak_stops_at_different_trigger():
    changes = [
        _change(change_id="1", trigger="account.general", payload={}, minutes_ago=4),
        _change(change_id="2", trigger="account.general", payload={}, minutes_ago=3),
        _change(change_id="x", trigger="account.display", payload={}, minutes_ago=2),
        _change(change_id="3", trigger="account.general", payload={}, minutes_ago=1),
    ]
    streak = collect_same_trigger_streak(changes, "account.general")
    assert [entry["id"] for entry in streak] == ["3"]


def test_keeps_first_on_off_pair():
    off = _general_payload(show_utc=False)
    on = _general_payload(show_utc=True)
    changes = [
        _change(change_id="c1", trigger="account.general", payload=off, minutes_ago=3),
    ]
    assert find_redundant_change_ids(changes, trigger="account.general", new_payload=on) == []


def test_flattens_on_off_on_back_to_first_state():
    off = _general_payload(show_utc=False)
    on = _general_payload(show_utc=True)
    streak = [
        _change(change_id="c1", trigger="account.general", payload=off, minutes_ago=3),
        _change(change_id="c2", trigger="account.general", payload=on, minutes_ago=2),
    ]
    assert redundant_change_ids_to_drop(streak, off) == ["c2"]


def test_flattens_second_on_off_pair():
    off = _general_payload(show_utc=False)
    on = _general_payload(show_utc=True)
    changes = [
        _change(change_id="c1", trigger="account.general", payload=off, minutes_ago=4),
        _change(change_id="c2", trigger="account.general", payload=on, minutes_ago=3),
        _change(change_id="c3", trigger="account.general", payload=off, minutes_ago=2),
    ]
    assert find_redundant_change_ids(changes, trigger="account.general", new_payload=on) == ["c3"]
    assert find_redundant_change_id(changes, trigger="account.general", new_payload=on) == "c3"


def test_redundant_change_ids_to_drop_requires_two_entry_streak():
    off = _general_payload(show_utc=False)
    on = _general_payload(show_utc=True)
    assert redundant_change_ids_to_drop([], on) == []
    assert redundant_change_ids_to_drop([{"payload": off, "id": "a"}], on) == []


def test_ignores_changes_outside_window():
    off = _general_payload(show_utc=False)
    on = _general_payload(show_utc=True)
    now = datetime.now(timezone.utc)
    stale = now - CHANGE_FLATTEN_WINDOW - timedelta(seconds=1)
    changes = [
        {
            "id": "old",
            "trigger": "account.general",
            "payload": off,
            "created_at": stale.isoformat(),
        },
        _change(change_id="c2", trigger="account.general", payload=on, minutes_ago=2),
    ]
    assert find_redundant_change_ids(changes, trigger="account.general", new_payload=off, now=now) == []
