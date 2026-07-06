from __future__ import annotations

from typing import Any

from brokerai.bots.researcher.rss_feeds import RSS_CATEGORIES, normalize_rss_categories
from brokerai.market_sessions import TRADING_SESSIONS, TRADING_SESSION_IDS, normalize_market_indicators
from brokerai.provider_capabilities import capability_label
from brokerai.research_markets import get_market, normalize_market_id, normalize_market_offset_hours

_SESSION_NAMES = {session.id: session.name for session in TRADING_SESSIONS}

_SCHEDULE_MODE_LABELS = {
    "daily": "Daily at market time",
    "daily_time": "Daily at specific time",
    "interval": "Fixed interval",
}


def join_change_labels(labels: list[str]) -> str:
    """Join one or more change descriptions for display in the backup table."""
    cleaned = [label.strip() for label in labels if label and label.strip()]
    return "; ".join(cleaned)


def _toggle_label(name: str, enabled: bool) -> str:
    state = "enabled" if enabled else "disabled"
    return f"{name} {state}"


def _market_label(market_id: str) -> str:
    market = get_market(normalize_market_id(market_id))
    return market.label if market else market_id


def _offset_phrase(offset_hours: int, *, anchor: str) -> str:
    offset = normalize_market_offset_hours(offset_hours)
    if offset == 0:
        return f"at market {anchor}"
    if offset < 0:
        hours = abs(offset)
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit} before {anchor}"
    unit = "hour" if offset == 1 else "hours"
    return f"{offset} {unit} after {anchor}"


def _contributors_signature(contributors: Any) -> tuple[tuple[str, str, bool], ...]:
    rows: list[tuple[str, str, bool]] = []
    for entry in contributors or []:
        if not isinstance(entry, dict):
            continue
        model_id = str(entry.get("model_id") or "").strip()
        if not model_id:
            continue
        rows.append(
            (
                model_id,
                str(entry.get("reasoning_effort") or ""),
                bool(entry.get("enabled", True)),
            )
        )
    return tuple(sorted(rows))


def _rss_category_label(category_id: str) -> str:
    meta = RSS_CATEGORIES.get(category_id) or {}
    return str(meta.get("label") or category_id.replace("_", " ").title())


def describe_general_settings_change(
    before: dict[str, Any],
    *,
    timezone_auto: bool,
    timezone: str | None,
    show_utc_times: bool,
    time_format: str,
) -> str:
    """Describe general settings mutations relative to the saved user record."""
    labels: list[str] = []

    if bool(before.get("timezone_auto")) != timezone_auto:
        labels.append(_toggle_label("Use automatic timezone", timezone_auto))

    if bool(before.get("show_utc_times")) != show_utc_times:
        labels.append(_toggle_label("Always Show UTC Time", show_utc_times))

    if str(before.get("time_format") or "24h") != time_format:
        fmt = "12-hour" if time_format == "12h" else "24-hour"
        labels.append(f"Time format set to {fmt}")

    before_tz = before.get("timezone")
    if not timezone_auto and str(before_tz or "") != str(timezone or ""):
        labels.append(f"Timezone set to {timezone or 'UTC'}")

    return join_change_labels(labels)


def describe_market_indicators_change(
    before: dict[str, bool],
    after: dict[str, bool],
) -> str:
    """Describe nav market-indicator toggles (Display settings)."""
    before_norm = normalize_market_indicators(before)
    after_norm = normalize_market_indicators(after)
    labels: list[str] = []

    for session_id in TRADING_SESSION_IDS:
        old = bool(before_norm.get(session_id, True))
        new = bool(after_norm.get(session_id, True))
        if old == new:
            continue
        name = _SESSION_NAMES.get(session_id, session_id.title())
        labels.append(f"{name} market {'enabled' if new else 'disabled'}")

    return join_change_labels(labels)


def describe_asset_settings_change(
    asset_class: str,
    before: dict[str, Any],
    *,
    enabled: bool,
    enabled_sessions: dict[str, bool] | None = None,
    enabled_pairs: list[str] | None = None,
    pair_order: list[str] | None = None,
    primary_exchange: str | None = None,
) -> str:
    """Describe broker asset-class settings mutations."""
    title = asset_class.replace("_", " ").title()
    labels: list[str] = []

    if bool(before.get("enabled")) != enabled:
        labels.append(_toggle_label(f"{title} broker", enabled))

    if asset_class == "forex" and enabled_sessions is not None:
        before_sessions = dict(before.get("enabled_sessions") or {})
        for session_id in TRADING_SESSION_IDS:
            old = bool(before_sessions.get(session_id, True))
            new = bool(enabled_sessions.get(session_id, True))
            if old == new:
                continue
            name = _SESSION_NAMES.get(session_id, session_id.title())
            labels.append(f"{name} trading session {'enabled' if new else 'disabled'}")

    if enabled_pairs is not None:
        before_pairs = list(before.get("enabled_pairs") or [])
        if before_pairs != list(enabled_pairs):
            before_set = set(before_pairs)
            after_set = set(enabled_pairs)
            added = sorted(after_set - before_set)
            removed = sorted(before_set - after_set)
            if added and not removed:
                labels.append(f"Forex pairs added: {', '.join(added)}")
            elif removed and not added:
                labels.append(f"Forex pairs removed: {', '.join(removed)}")
            else:
                labels.append("Forex pairs updated")

    if pair_order is not None and list(before.get("pair_order") or []) != list(pair_order):
        labels.append("Forex pair order updated")

    if primary_exchange is not None and str(before.get("primary_exchange") or "") != str(primary_exchange or ""):
        labels.append(f"Primary exchange set to {primary_exchange or 'none'}")

    return join_change_labels(labels)


def describe_system_update_change(
    before: dict[str, Any],
    *,
    update_track: str,
    branch: str,
    release: str,
    auto_update: bool,
) -> str:
    """Describe system update preference mutations."""
    labels: list[str] = []

    if str(before.get("update_track") or "") != update_track:
        track_labels = {
            "branch": "Branch track",
            "release": "Release track",
            "latest-release": "Latest release track",
            "next-major": "Next major release track",
        }
        labels.append(f"Update track set to {track_labels.get(update_track, update_track)}")

    if str(before.get("branch") or "") != branch and update_track == "branch":
        labels.append(f"Update branch set to {branch}")

    if str(before.get("release") or "") != release and update_track == "release":
        labels.append(f"Pinned release set to {release or 'none'}")

    if bool(before.get("auto_update")) != auto_update and update_track != "release":
        labels.append(_toggle_label("Auto-update", auto_update))

    return join_change_labels(labels)


def describe_backup_schedule_change(
    before: dict[str, Any],
    updates: dict[str, Any],
) -> str:
    """Describe automatic backup schedule mutations."""
    labels: list[str] = []

    if "enabled" in updates and bool(before.get("enabled")) != bool(updates["enabled"]):
        labels.append(_toggle_label("Scheduled backups", bool(updates["enabled"])))

    if "mode" in updates and str(before.get("mode") or "daily") != str(updates["mode"]):
        mode = str(updates["mode"])
        labels.append(f"Schedule mode set to {_SCHEDULE_MODE_LABELS.get(mode, mode)}")

    if "daily_market_id" in updates and str(before.get("daily_market_id") or "") != str(
        updates["daily_market_id"]
    ):
        labels.append(f"Schedule market set to {_market_label(str(updates['daily_market_id']))}")

    if "daily_offset_hours" in updates and int(before.get("daily_offset_hours") or 0) != int(
        updates["daily_offset_hours"]
    ):
        phrase = _offset_phrase(int(updates["daily_offset_hours"]), anchor="open")
        labels.append(f"Schedule run time set to {phrase}")

    if "daily_time" in updates and str(before.get("daily_time") or "") != str(updates["daily_time"]):
        labels.append(f"Schedule run time set to {updates['daily_time']}")

    if "interval_hours" in updates and int(before.get("interval_hours") or 0) != int(
        updates["interval_hours"]
    ):
        hours = int(updates["interval_hours"])
        labels.append(f"Backup interval set to every {hours} hour{'s' if hours != 1 else ''}")

    if "full_retention" in updates and int(before.get("full_retention") or 0) != int(
        updates["full_retention"]
    ):
        labels.append(f"Full backup retention set to {int(updates['full_retention'])}")

    if "change_retention" in updates and int(before.get("change_retention") or 0) != int(
        updates["change_retention"]
    ):
        labels.append(f"Change history retention set to {int(updates['change_retention'])}")

    return join_change_labels(labels)


def _describe_research_data_sources_change(
    before_sources: dict[str, Any],
    after_sources: dict[str, Any],
) -> list[str]:
    labels: list[str] = []

    if bool(before_sources.get("newsapi", True)) != bool(after_sources.get("newsapi", True)):
        labels.append(_toggle_label("NewsAPI data source", bool(after_sources.get("newsapi", True))))

    if bool(before_sources.get("rss_enabled")) != bool(after_sources.get("rss_enabled")):
        labels.append(_toggle_label("RSS feeds", bool(after_sources.get("rss_enabled"))))

    before_rss = normalize_rss_categories(before_sources.get("rss_categories"))
    after_rss = normalize_rss_categories(after_sources.get("rss_categories"))
    for category_id in RSS_CATEGORIES:
        old = bool(before_rss.get(category_id, True))
        new = bool(after_rss.get(category_id, True))
        if old == new:
            continue
        labels.append(
            f"{_rss_category_label(category_id)} RSS {'enabled' if new else 'disabled'}"
        )

    if bool(before_sources.get("web_search_enabled")) != bool(after_sources.get("web_search_enabled")):
        labels.append(_toggle_label("Web search", bool(after_sources.get("web_search_enabled"))))

    if str(before_sources.get("web_search_model_id") or "") != str(
        after_sources.get("web_search_model_id") or ""
    ):
        labels.append("Web search model updated")

    if bool(before_sources.get("x_search_enabled")) != bool(after_sources.get("x_search_enabled")):
        labels.append(_toggle_label("X search", bool(after_sources.get("x_search_enabled"))))

    if str(before_sources.get("x_search_model_id") or "") != str(
        after_sources.get("x_search_model_id") or ""
    ):
        labels.append("X search model updated")

    return labels


def describe_research_settings_change(
    before: dict[str, Any],
    *,
    contributor_models: list[dict[str, Any]] | None = None,
    synthesis_model_id: str | None = None,
    synthesis_reasoning_effort: str | None = None,
    data_sources: dict[str, Any] | None = None,
    daily_report_enabled: bool | None = None,
    daily_report_market_id: str | None = None,
    daily_report_market_offset_hours: int | None = None,
) -> str:
    """Describe daily research report settings mutations."""
    labels: list[str] = []

    if contributor_models is not None:
        before_sig = _contributors_signature(before.get("contributor_models"))
        after_sig = _contributors_signature(contributor_models)
        if before_sig != after_sig:
            labels.append("Contributor models updated")

    if synthesis_model_id is not None and str(before.get("synthesis_model_id") or "") != str(
        synthesis_model_id or ""
    ):
        labels.append("Synthesis model updated")

    if (
        synthesis_reasoning_effort is not None
        and str(before.get("synthesis_reasoning_effort") or "") != synthesis_reasoning_effort
    ):
        labels.append(f"Synthesis reasoning effort set to {synthesis_reasoning_effort}")

    if data_sources is not None:
        before_sources = dict(before.get("data_sources") or {})
        labels.extend(_describe_research_data_sources_change(before_sources, data_sources))

    if daily_report_enabled is not None and bool(before.get("daily_report_enabled")) != daily_report_enabled:
        labels.append(_toggle_label("Daily report", daily_report_enabled))

    if daily_report_market_id is not None and str(before.get("daily_report_market_id") or "") != str(
        normalize_market_id(daily_report_market_id)
    ):
        labels.append(f"Daily report market set to {_market_label(daily_report_market_id)}")

    if daily_report_market_offset_hours is not None and int(
        before.get("daily_report_market_offset_hours") or 0
    ) != normalize_market_offset_hours(daily_report_market_offset_hours):
        phrase = _offset_phrase(daily_report_market_offset_hours, anchor="open")
        labels.append(f"Daily report run time set to {phrase}")

    return join_change_labels(labels)


def describe_weekly_research_settings_change(
    before: dict[str, Any],
    *,
    weekly_brief_enabled: bool | None = None,
    weekly_brief_model_id: str | None = None,
    weekly_brief_reasoning_effort: str | None = None,
    weekly_brief_market_id: str | None = None,
    weekly_brief_market_offset_hours: int | None = None,
    weekly_debrief_enabled: bool | None = None,
    weekly_debrief_model_id: str | None = None,
    weekly_debrief_reasoning_effort: str | None = None,
    weekly_debrief_market_id: str | None = None,
    weekly_debrief_market_offset_hours: int | None = None,
) -> str:
    """Describe weekly brief/debrief settings mutations."""
    labels: list[str] = []

    if weekly_brief_enabled is not None and bool(before.get("weekly_brief_enabled")) != weekly_brief_enabled:
        labels.append(_toggle_label("Weekly brief", weekly_brief_enabled))

    if weekly_brief_model_id is not None and str(before.get("weekly_brief_model_id") or "") != str(
        weekly_brief_model_id or ""
    ):
        labels.append("Weekly brief model updated")

    if (
        weekly_brief_reasoning_effort is not None
        and str(before.get("weekly_brief_reasoning_effort") or "") != weekly_brief_reasoning_effort
    ):
        labels.append(f"Weekly brief reasoning effort set to {weekly_brief_reasoning_effort}")

    if weekly_brief_market_id is not None and str(before.get("weekly_brief_market_id") or "") != str(
        normalize_market_id(weekly_brief_market_id)
    ):
        labels.append(f"Weekly brief market set to {_market_label(weekly_brief_market_id)}")

    if weekly_brief_market_offset_hours is not None and int(
        before.get("weekly_brief_market_offset_hours") or 0
    ) != normalize_market_offset_hours(weekly_brief_market_offset_hours):
        phrase = _offset_phrase(weekly_brief_market_offset_hours, anchor="open")
        labels.append(f"Weekly brief run time set to {phrase}")

    if weekly_debrief_enabled is not None and bool(before.get("weekly_debrief_enabled")) != weekly_debrief_enabled:
        labels.append(_toggle_label("Weekly debrief", weekly_debrief_enabled))

    if weekly_debrief_model_id is not None and str(before.get("weekly_debrief_model_id") or "") != str(
        weekly_debrief_model_id or ""
    ):
        labels.append("Weekly debrief model updated")

    if (
        weekly_debrief_reasoning_effort is not None
        and str(before.get("weekly_debrief_reasoning_effort") or "") != weekly_debrief_reasoning_effort
    ):
        labels.append(f"Weekly debrief reasoning effort set to {weekly_debrief_reasoning_effort}")

    if weekly_debrief_market_id is not None and str(before.get("weekly_debrief_market_id") or "") != str(
        normalize_market_id(weekly_debrief_market_id)
    ):
        labels.append(f"Weekly debrief market set to {_market_label(weekly_debrief_market_id)}")

    if weekly_debrief_market_offset_hours is not None and int(
        before.get("weekly_debrief_market_offset_hours") or 0
    ) != normalize_market_offset_hours(weekly_debrief_market_offset_hours):
        phrase = _offset_phrase(weekly_debrief_market_offset_hours, anchor="close")
        labels.append(f"Weekly debrief run time set to {phrase}")

    return join_change_labels(labels)


def describe_rss_feeds_change(
    before_sources: dict[str, Any],
    *,
    rss_enabled: bool | None,
    rss_categories: dict[str, bool],
) -> str:
    """Describe RSS feed category toggles."""
    labels: list[str] = []
    after_sources = dict(before_sources)

    if rss_enabled is not None:
        after_sources["rss_enabled"] = rss_enabled
        if bool(before_sources.get("rss_enabled")) != rss_enabled:
            labels.append(_toggle_label("RSS feeds", rss_enabled))

    if rss_categories:
        before_rss = normalize_rss_categories(before_sources.get("rss_categories"))
        merged = dict(before_rss)
        for key, enabled in rss_categories.items():
            if key in merged:
                merged[key] = bool(enabled)
        after_sources["rss_categories"] = merged
        for category_id in RSS_CATEGORIES:
            if category_id not in rss_categories:
                continue
            old = bool(before_rss.get(category_id, True))
            new = bool(merged.get(category_id, True))
            if old == new:
                continue
            labels.append(
                f"{_rss_category_label(category_id)} RSS {'enabled' if new else 'disabled'}"
            )

    return join_change_labels(labels)


def describe_ai_model_update(
    before: dict[str, Any],
    *,
    title: str | None,
    base_url: str | None,
    model_name: str | None,
    enabled: bool | None,
    api_key_changed: bool,
) -> str:
    """Describe AI model field mutations."""
    model_title = str(before.get("title") or "AI model")
    labels: list[str] = []

    if title is not None and str(before.get("title") or "") != title:
        labels.append(f"Model renamed to {title}")

    if base_url is not None and str(before.get("base_url") or "") != base_url:
        labels.append(f"{model_title} base URL updated")

    if model_name is not None and str(before.get("model_name") or "") != model_name:
        labels.append(f"{model_title} model name set to {model_name}")

    if enabled is not None and bool(before.get("enabled")) != enabled:
        labels.append(_toggle_label(model_title, enabled))

    if api_key_changed:
        labels.append(f"{model_title} API key updated")

    return join_change_labels(labels)


def describe_model_capabilities_change(
    before: dict[str, bool],
    after: dict[str, bool],
    *,
    model_title: str,
) -> str:
    """Describe per-model data-connection capability toggles."""
    labels: list[str] = []
    keys = sorted(set(before) | set(after))

    for key in keys:
        old = bool(before.get(key, False))
        new = bool(after.get(key, False))
        if old == new:
            continue
        name = capability_label(key)
        labels.append(f"{model_title} {name} {'enabled' if new else 'disabled'}")

    return join_change_labels(labels)


def describe_oanda_connection_change(
    before: dict[str, Any],
    *,
    environment: str,
    account_id: str,
    access_token_changed: bool,
) -> str:
    """Describe OANDA exchange connection mutations."""
    labels: list[str] = []

    if not before.get("access_token") and access_token_changed:
        labels.append("OANDA connected")
    elif before.get("access_token") and access_token_changed:
        labels.append("OANDA access token updated")

    if str(before.get("environment") or "") != environment:
        labels.append(f"OANDA environment set to {environment}")

    if str(before.get("account_id") or "") != account_id:
        labels.append(f"OANDA account set to {account_id}")

    return join_change_labels(labels)


def describe_api_connection_change(
    name: str,
    before: dict[str, Any],
    *,
    enabled: bool,
    api_key_changed: bool,
    removed: bool = False,
) -> str:
    """Describe NewsAPI/Massive connection mutations."""
    if removed:
        return f"{name} connection removed"

    labels: list[str] = []
    if not before.get("api_key") and api_key_changed:
        labels.append(f"{name} API key added")
    elif before.get("api_key") and api_key_changed:
        labels.append(f"{name} API key updated")

    if bool(before.get("enabled")) != enabled:
        labels.append(_toggle_label(name, enabled))

    return join_change_labels(labels)


def describe_strategy_update(
    before: dict[str, Any],
    *,
    name: str | None,
    description: str | None,
    params: dict[str, Any] | None,
    instrument_selection: dict[str, list[str]] | None,
    enabled: bool | None,
) -> str:
    """Describe strategy patch mutations."""
    strategy_name = str(before.get("name") or "Strategy")
    labels: list[str] = []

    if name is not None and str(before.get("name") or "") != name:
        labels.append(f"Strategy renamed to {name}")

    if description is not None and str(before.get("description") or "") != description:
        labels.append(f"{strategy_name} description updated")

    if enabled is not None and bool(before.get("enabled")) != enabled:
        labels.append(_toggle_label(strategy_name, enabled))

    if params is not None and dict(before.get("params") or {}) != params:
        labels.append(f"{strategy_name} parameters updated")

    if instrument_selection is not None and dict(before.get("instrument_selection") or {}) != instrument_selection:
        labels.append(f"{strategy_name} instruments updated")

    return join_change_labels(labels)
