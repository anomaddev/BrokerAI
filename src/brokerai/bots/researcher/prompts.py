from __future__ import annotations

from collections import defaultdict
from datetime import date

from brokerai.db.repositories.asset_settings import FOREX_PAIR_CATALOG
from brokerai.research_constants import DAILY_REPORT_REASONING_EFFORT, REASONING_EFFORT_OPTIONS

# Cap injected historical context so large archives stay within token budgets.
MAX_HISTORY_CHARS = 60_000

_ANALYST_SYSTEM_PROMPT = """\
You are a senior forex market analyst preparing an institutional daily research brief.

Use rigorous, step-by-step reasoning before stating conclusions:
1. Extract concrete facts, dates, and figures from each article.
2. Map each fact to the relevant pair(s) in the group and note second-order effects.
3. Identify conflicting signals and explain which evidence weighs more.
4. Weigh macro drivers (rates, inflation, growth, risk sentiment, central banks, geopolitics).
5. Synthesize a coherent view for the currency group, then drill into each pair individually.
6. For each pair, note pair-specific drivers (cross-currency dynamics, relative rates, idiosyncratic news) that may differ from the group view.
7. For each pair, derive a concrete daily trading strategy: directional bias, how to enter, where to take profit, and what invalidates the idea — written so an automated system can parse and act on it through the session.

Be explicit about uncertainty, assumptions, and what would invalidate your view.
Ground every claim in the supplied articles; do not invent events or data.
Articles are tagged with the data source they came from (e.g. NewsAPI, RSS, web search,
X search). Weigh established financial newswires more heavily than social posts, and
treat X/social items as sentiment signals that need corroboration.
When pair-level and group-level views diverge, explain why."""

_HISTORY_SYSTEM_ADDENDUM = """\

You are also given historical weekly debriefs from prior weeks. Use them for trend
continuity: compare today's evidence against prior themes and signals, and note
where the view continues, reverses, or has become stale. Treat the debriefs as
context only, not as new news."""

_MARKET_CLOSED_SYSTEM_ADDENDUM = """\

The forex market is currently closed (weekend). Frame your analysis for Monday
open positioning rather than intraday execution. Emphasize weekend headlines, gap
risk at the open, the week-ahead calendar of catalysts, and whether weekend
developments change the prior week's bias. Where appropriate, favor waiting for
confirmation at the open over committing ahead of it. Daily strategy fields should
describe Monday-open setups (gap-and-go, fade the gap, wait for first-hour range)
rather than intraday session timing."""


def _forex_primary_order() -> tuple[str, ...]:
    order: list[str] = []
    seen: set[str] = set()
    for pair in FOREX_PAIR_CATALOG:
        primary = pair.split("/", 1)[0]
        if primary not in seen:
            seen.add(primary)
            order.append(primary)
    return tuple(order)


def group_forex_pairs(pairs: list[str]) -> dict[str, list[str]]:
    """Group enabled pairs by primary currency in catalog order (not user priority)."""
    enabled = set(pairs)
    groups: dict[str, list[str]] = defaultdict(list)
    for pair in FOREX_PAIR_CATALOG:
        if pair not in enabled:
            continue
        primary = pair.split("/", 1)[0]
        groups[primary].append(pair)
    return {primary: groups[primary] for primary in _forex_primary_order() if primary in groups}


def news_queries_for_group(primary: str, pairs: list[str]) -> list[str]:
    """Progressively broader NewsAPI queries for a currency group."""
    currency_names = {
        "USD": "US dollar",
        "EUR": "euro",
        "GBP": "British pound",
        "JPY": "Japanese yen",
        "AUD": "Australian dollar",
        "CAD": "Canadian dollar",
        "CHF": "Swiss franc",
        "NZD": "New Zealand dollar",
    }
    name = currency_names.get(primary, primary)
    counters = sorted({p.split("/", 1)[1] for p in pairs if "/" in p})
    counter_names = [currency_names.get(code, code) for code in counters]
    counter_terms = " OR ".join(dict.fromkeys([*counters, *counter_names]))
    pair_terms = " OR ".join(f'"{pair}"' for pair in pairs[:6])

    queries = [
        f'({primary} OR "{name}") AND (forex OR currency OR "exchange rate" OR "central bank")',
    ]
    if counter_terms:
        queries.append(f'({primary} OR "{name}") AND ({counter_terms} OR forex OR currency)')
    if pair_terms:
        queries.append(f'({primary} OR "{name}" OR forex) AND ({pair_terms})')
    queries.append(f"{primary} OR \"{name}\" OR \"{primary} forex\"")
    return list(dict.fromkeys(queries))


def news_query_for_group(primary: str, pairs: list[str]) -> str:
    """Primary (broadest) NewsAPI query for a currency group."""
    return news_queries_for_group(primary, pairs)[0]


def is_market_closed(report_date: str | date) -> bool:
    """True on Saturday/Sunday (UTC), when the forex market is closed."""
    d = report_date if isinstance(report_date, date) else date.fromisoformat(report_date)
    return d.weekday() >= 5


def _format_historical_context(historical_context: str | None) -> str | None:
    if not historical_context or not historical_context.strip():
        return None

    text = historical_context.strip()
    if len(text) > MAX_HISTORY_CHARS:
        # Keep the most recent weeks (newest content is at the end).
        text = text[-MAX_HISTORY_CHARS:]
        text = "(older weeks truncated)\n\n" + text
    return text


def build_analysis_messages(
    primary: str,
    pairs: list[str],
    articles: list[dict],
    *,
    historical_context: str | None = None,
    market_closed: bool = False,
) -> list[dict[str, str]]:
    history = _format_historical_context(historical_context)

    system_prompt = _ANALYST_SYSTEM_PROMPT
    if history:
        system_prompt += _HISTORY_SYSTEM_ADDENDUM
    if market_closed:
        system_prompt += _MARKET_CLOSED_SYSTEM_ADDENDUM

    user_lines = [
        f"Analyze news for the {primary} currency group.",
        f"Forex pairs in this group: {', '.join(pairs)}",
        "",
    ]

    if market_closed:
        user_lines.extend(
            [
                "Note: the market is closed for the weekend. Produce a Monday-open "
                "outlook rather than an intraday view.",
                "",
            ]
        )

    if history:
        user_lines.extend(
            [
                "Historical weekly debriefs (last 8 weeks — use for trend continuity; "
                "do not treat as new news):",
                history,
                "",
            ]
        )

    user_lines.append("Articles (each tagged with the data source it came from):")
    for idx, article in enumerate(articles, start=1):
        user_lines.append(f"{idx}. {article.get('title', '')}")
        if article.get("data_source"):
            user_lines.append(f"   Via: {article['data_source']}")
        if article.get("source"):
            user_lines.append(f"   Source: {article['source']}")
        if article.get("description"):
            user_lines.append(f"   Summary: {article['description']}")
        if article.get("url"):
            user_lines.append(f"   URL: {article['url']}")
        user_lines.append("")

    user_lines.extend(
        [
            "Write a detailed markdown section with these headings (start each with ####):",
            "",
            "#### Reasoning",
            "Walk through your analysis step by step: key facts, pair-by-pair implications, "
            "conflicts, and how you weighed the evidence.",
            "",
            "#### Summary",
            "Key themes for this currency group.",
            "",
            "#### Tone",
            "bullish / bearish / neutral for the group, with brief justification.",
            "",
            "#### Signal",
            "buy / sell / hold / mixed for the group.",
            "",
            "#### Confidence",
            "low / medium / high, with what would raise or lower confidence.",
            "",
            "#### Key events and levels",
            "Upcoming catalysts, support/resistance or levels to watch.",
            "",
            "#### Pair guidance",
            f"Brief pair-level outlook for every pair in this group ({', '.join(pairs)}). "
            "For each pair, use a #### subheading with the pair name (e.g. #### EUR/USD) and include:",
            "- **Tone** — bullish / bearish / neutral for this pair specifically",
            "- **Signal** — buy / sell / hold / mixed",
            "- **Note** — 1–3 sentences on pair-specific drivers, cross-rate dynamics, or "
            "divergence from the group view",
            "- **Daily strategy** — a concrete, session-level trade plan using these sub-bullets "
            "(use the exact labels so downstream systems can parse them):",
            "  - **Approach** — one of: buy dip / sell rally / breakout long / breakout short / "
            "range trade / fade / stand aside",
            "  - **Entry** — specific price level(s) or condition to initiate (e.g. \"on break above "
            "1.0850\" or \"fade rallies into 186.30\")",
            "  - **Targets** — take-profit level(s) or conditions",
            "  - **Invalidation** — stop level or event that voids the trade idea",
            "  - **Timing** — session or event windows to act or avoid (e.g. \"enter after London open\", "
            "\"no new risk 30 min before US CPI\")",
            "  - **Conviction** — low / medium / high for this specific trade idea",
            "",
            "Cover every listed pair. When Signal is hold or mixed, Approach should usually be "
            "stand aside or range trade unless a clear conditional setup exists.",
            "",
            "Be thorough and specific. Prefer depth over brevity for group sections; "
            "keep pair guidance brief but make Daily strategy precise and machine-readable.",
        ]
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n".join(user_lines)},
    ]


def build_analysis_prompt(primary: str, pairs: list[str], articles: list[dict]) -> str:
    """Legacy single-string prompt; prefer build_analysis_messages for daily reports."""
    messages = build_analysis_messages(primary, pairs, articles)
    return messages[1]["content"]


_SYNTHESIS_SYSTEM_PROMPT = """\
You are the chief market strategist consolidating several analysts' daily forex
briefs into one authoritative institutional report.

You are given the full daily report from each contributing analyst model. They were
all given the same source articles, so differences reflect genuine analytical
disagreement, not different evidence. Your job is to produce a single, decisive brief:

1. Inventory the themes each analyst raised and group equivalent points together.
2. Flag where analysts disagree on tone, signal, or confidence, and adjudicate which
   reasoning is better supported by the evidence they cite.
3. Produce a weighted consensus per currency group and per pair. When analysts agree,
   state the view with higher confidence; when they diverge, present the balanced view
   and explain the split.
4. Confidence must reflect inter-model agreement: high only when analysts broadly
   concur and evidence is strong; lower when they conflict.
5. Reconcile each pair's daily trading strategy from the analyst briefs into one
   actionable plan per instrument, suitable for downstream execution or re-analysis.

Do not invent facts beyond what the analysts reported. Do not simply concatenate the
inputs — reconcile them into one coherent voice. Be specific and actionable."""


def build_synthesis_messages(
    reports: list[dict[str, str]],
    *,
    report_date: str,
    historical_context: str | None = None,
    market_closed: bool = False,
) -> list[dict[str, str]]:
    """Build messages that merge multiple contributor reports into a final brief.

    Each entry in ``reports`` is ``{"model": <title>, "content": <markdown>}``.
    """
    history = _format_historical_context(historical_context)

    system_prompt = _SYNTHESIS_SYSTEM_PROMPT
    if history:
        system_prompt += _HISTORY_SYSTEM_ADDENDUM
    if market_closed:
        system_prompt += _MARKET_CLOSED_SYSTEM_ADDENDUM

    user_lines = [
        f"Consolidate the following {len(reports)} analyst forex briefs for {report_date} "
        "into one unified daily report.",
        "",
    ]

    if market_closed:
        user_lines.extend(
            [
                "Note: the market is closed for the weekend. Produce a Monday-open "
                "outlook rather than an intraday view.",
                "",
            ]
        )

    if history:
        user_lines.extend(
            [
                "Historical weekly debriefs (last 8 weeks — use for trend continuity; "
                "do not treat as new news):",
                history,
                "",
            ]
        )

    for report in reports:
        model_label = report.get("model") or "Analyst"
        user_lines.append(f"===== Analyst: {model_label} =====")
        user_lines.append(report.get("content", "").strip())
        user_lines.append("")

    user_lines.extend(
        [
            "Produce the final consolidated report in markdown.",
            "",
            "Start with a top-level `## Forex` heading. For each currency group, use a "
            "`### {PRIMARY} Group ({pairs})` heading, then the following `####` subsections:",
            "",
            "#### Reasoning",
            "Synthesised analysis: shared themes, where analysts agreed or disagreed, and "
            "how you weighed conflicting views.",
            "",
            "#### Summary",
            "Key themes for the group.",
            "",
            "#### Tone",
            "bullish / bearish / neutral, reflecting the consensus.",
            "",
            "#### Signal",
            "buy / sell / hold / mixed.",
            "",
            "#### Confidence",
            "low / medium / high — explicitly reflecting how much the analysts agreed.",
            "",
            "#### Key events and levels",
            "Upcoming catalysts and support/resistance levels.",
            "",
            "#### Pair guidance",
            "For every pair, a `#### {PAIR}` subheading with **Tone**, **Signal**, a concise "
            "**Note** on pair-specific drivers and any analyst disagreement, and a reconciled "
            "**Daily strategy** block with these sub-bullets (use the exact labels):",
            "  - **Approach** — buy dip / sell rally / breakout long / breakout short / "
            "range trade / fade / stand aside",
            "  - **Entry** — specific level(s) or entry condition",
            "  - **Targets** — take-profit level(s)",
            "  - **Invalidation** — stop or thesis-break condition",
            "  - **Timing** — when to act or avoid through the session",
            "  - **Conviction** — low / medium / high",
            "",
            "When analysts proposed different strategies for the same pair, pick the best-supported "
            "plan and note the rejected alternative briefly in **Note** or **Invalidation**.",
            "",
            "Cover every currency group and pair that appears in the analyst briefs. "
            "Be decisive and institutional in tone.",
        ]
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n".join(user_lines)},
    ]


_WEEKLY_BRIEF_SYSTEM_PROMPT = """\
You are the chief market strategist preparing a weekly opening brief for an
automated forex trading system.

Your audience is a bot that will plan the week's decisions and act at market open.
Produce a decisive, actionable brief — not a recap of every daily report.

Focus on:
1. The dominant macro and risk themes carrying into the new week.
2. Where weekend or pre-open dailies agree or disagree, and your adjudication.
3. Concrete actions to take at or shortly after open (per major pair or group).
4. Key calendar catalysts for the week and what would invalidate the plan.

Be specific about entry logic, timing windows, and stand-aside conditions.
Ground claims in the supplied daily reports and news; do not invent events."""


_WEEKLY_DEBRIEF_SYSTEM_PROMPT = """\
You are the chief market strategist writing a weekly debrief for an automated
forex trading system's long-term memory.

Summarize the completed trading week for future research runs:
1. Major news themes and how they evolved Mon–Fri.
2. Price action and volatility patterns implied by the daily reports.
3. Where the week's brief (if provided) was right, wrong, or incomplete.
4. Actionable lessons and biases to carry into future weeks.

Write for machine consumption: structured markdown, explicit themes, and clear
continuity signals. Do not invent trades or P&L — execution history is not yet
available. Do not simply concatenate daily reports; synthesize them."""


_WEEKLY_BRIEF_USER_TEMPLATE = """\
Produce the weekly opening brief for week of {week_start}.

Inputs below include off-market weekend dailies (if any), the open-day daily,
and optional fresh news articles.

{daily_section}

{news_section}

Produce markdown with these top-level sections:
## Week outlook
## Macro themes
## Open actions
## Calendar and risks
## Pair priorities

Under **Open actions**, list concrete setups the bot should consider at open with
Approach, Entry, Targets, Invalidation, Timing, and Conviction per instrument."""


_WEEKLY_DEBRIEF_USER_TEMPLATE = """\
Produce the weekly debrief for the completed week of {week_start}.

Weekday daily reports:
{daily_section}

{brief_section}

{history_section}

Note any missing weekday dailies in a short **Coverage** subsection.

Produce markdown with:
## Week summary
## News and macro themes
## Price action and volatility
## Brief assessment
## Lessons for future weeks
## Coverage"""


def get_weekly_brief_prompt_preview() -> dict[str, str]:
    return {
        "system_prompt": _WEEKLY_BRIEF_SYSTEM_PROMPT.strip(),
        "user_template": _WEEKLY_BRIEF_USER_TEMPLATE.strip(),
    }


def get_weekly_debrief_prompt_preview() -> dict[str, str]:
    return {
        "system_prompt": _WEEKLY_DEBRIEF_SYSTEM_PROMPT.strip(),
        "user_template": _WEEKLY_DEBRIEF_USER_TEMPLATE.strip(),
    }


def _format_daily_entries(dailies: list[dict[str, str]]) -> str:
    if not dailies:
        return "(No daily reports available.)"
    parts: list[str] = []
    for entry in dailies:
        parts.append(f"===== Daily report: {entry['date']} =====")
        parts.append(entry.get("content", "").strip())
        parts.append("")
    return "\n".join(parts).strip()


def build_weekly_brief_messages(
    *,
    week_start: date,
    dailies: list[dict[str, str]],
    articles: list[dict] | None = None,
) -> list[dict[str, str]]:
    daily_section = _format_daily_entries(dailies)
    if articles:
        news_lines = ["Fresh news articles:"]
        for idx, article in enumerate(articles, start=1):
            news_lines.append(f"{idx}. {article.get('title', '')}")
            if article.get("data_source"):
                news_lines.append(f"   Via: {article['data_source']}")
            if article.get("description"):
                news_lines.append(f"   Summary: {article['description']}")
            news_lines.append("")
        news_section = "\n".join(news_lines).strip()
    else:
        news_section = "(No additional news fetched for this brief.)"

    user_content = _WEEKLY_BRIEF_USER_TEMPLATE.format(
        week_start=week_start.isoformat(),
        daily_section=daily_section,
        news_section=news_section,
    )
    return [
        {"role": "system", "content": _WEEKLY_BRIEF_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_weekly_debrief_messages(
    *,
    week_start: date,
    dailies: list[dict[str, str]],
    weekly_brief: str | None = None,
    historical_debriefs: str | None = None,
    missing_dates: list[str] | None = None,
) -> list[dict[str, str]]:
    daily_section = _format_daily_entries(dailies)
    brief_section = (
        f"Weekly brief for this week:\n{weekly_brief.strip()}"
        if weekly_brief and weekly_brief.strip()
        else "(No weekly brief was generated for this week.)"
    )
    history = _format_historical_context(historical_debriefs)
    history_section = (
        f"Prior weekly debriefs (context only):\n{history}"
        if history
        else "(No prior weekly debriefs available.)"
    )

    user_content = _WEEKLY_DEBRIEF_USER_TEMPLATE.format(
        week_start=week_start.isoformat(),
        daily_section=daily_section,
        brief_section=brief_section,
        history_section=history_section,
    )
    if missing_dates:
        user_content += (
            f"\n\nMissing weekday dailies: {', '.join(missing_dates)}. "
            "Note this under **Coverage**."
        )

    return [
        {"role": "system", "content": _WEEKLY_DEBRIEF_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
