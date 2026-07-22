"""Package completed backtest data and request AI strategy feedback.

Builds a compact context (run meta, params, stats, reconstructed trades,
sampled signals, trade-window candles, period summary) and calls an enabled
API-source model via ``analyze_with_model``. Feedback is stored on the run
doc as ``ai_feedback``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from brokerai.ai_strategy.daily_backtest import ORIGIN_AI_STRATEGY_DAILY
from brokerai.ai_strategy.learning import queue_learning_job
from brokerai.ai_strategy.memory_digest import merge_feedback_notes_into_digest
from brokerai.backtesting.feedback_suggestions import (
    ALLOWLIST_FOR_PROMPT,
    normalize_suggestions,
    parse_suggestions_from_markdown,
)
from brokerai.bots.data_manager.candle_schedule import timeframe_to_duration
from brokerai.bots.researcher.llm import analyze_with_model
from brokerai.db.repositories.ai_models import AiModelsRepository, bind_source_model
from brokerai.db.repositories.backtest_actions import BacktestActionsRepository
from brokerai.db.repositories.backtest_logs import BacktestLogsRepository
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUS_COMPLETED,
    BacktestRunsRepository,
)
from brokerai.db.repositories.backtest_settings import BacktestSettingsRepository
from brokerai.db.repositories.strategy_learning import StrategyMemoryDigestsRepository
from brokerai.research_constants import REASONING_EFFORT_OPTIONS
from brokerai.trading.data.candle_cache import CandleCache, OANDA_SOURCE

logger = logging.getLogger(__name__)

AI_FEEDBACK_STATUS_QUEUED = "queued"
AI_FEEDBACK_STATUS_RUNNING = "running"
AI_FEEDBACK_STATUS_COMPLETED = "completed"
AI_FEEDBACK_STATUS_FAILED = "failed"

AI_FEEDBACK_STATUSES = frozenset(
    {
        AI_FEEDBACK_STATUS_QUEUED,
        AI_FEEDBACK_STATUS_RUNNING,
        AI_FEEDBACK_STATUS_COMPLETED,
        AI_FEEDBACK_STATUS_FAILED,
    }
)

TRADE_KINDS = frozenset({"entry", "exit", "sl", "tp"})
EXIT_KINDS = frozenset({"exit", "sl", "tp"})
SIGNAL_SAMPLE_LIMIT = 40
FILTER_FAIL_SAMPLE_LIMIT = 40
EQUITY_FEEDBACK_MAX_POINTS = 50
CANDLE_WINDOW_BARS = 12
MAX_TRADE_WINDOWS = 40
MAX_WARN_LOGS = 30
MAX_CONTEXT_JSON_CHARS = 120_000

_FEEDBACK_SYSTEM_PROMPT = f"""\
You are an expert algorithmic trading coach reviewing a completed strategy backtest.

Your job is to give actionable feedback on where the strategy could improve — not
to rewrite the entire system from scratch.

Use rigorous reasoning:
1. Summarize what the backtest actually did (edge, trade count, win rate, drawdown).
2. Identify failure modes from losing trades, stop-outs, and filter failures.
3. Relate failures to the frozen strategy parameters (indicators, filters, exits, risk).
4. Propose concrete, testable parameter or rule changes (with why).
5. Call out overfitting risk: do not recommend fitting to a handful of trades.
6. Prefer changes that preserve live-parity constraints (no look-ahead, session/risk gates).

Respond in clear markdown with these sections:
## Summary
## What worked
## What hurt performance
## Suggested improvements
## Risks / caveats

After the markdown sections, append ONE fenced JSON block with structured suggestions
that map to UI-editable strategy params. Use only these paths:
{', '.join(ALLOWLIST_FOR_PROMPT)}

JSON shape:
```json
{{
  "suggestions": [
    {{
      "id": "atr_floor_jpy",
      "path": "filters.atr.min_value_jpy",
      "from": 0.0008,
      "to": 0.05,
      "rationale": "JPY ATR floor",
      "priority": 1,
      "test_alone": true
    }}
  ]
}}
```

Rules for JSON:
- Only include paths from the allowlist above.
- Prefer one-factor-at-a-time (set test_alone true; keep the list short).
- Do not invent unsupported features or EMA period retunes unless path is allowlisted.
- Be specific and grounded in the supplied data. Do not invent trades or metrics.
"""

_MEMORY_NOTES_JSON_FOOTER = """\
After the markdown sections, append ONE fenced JSON block with memory notes:
```json
{
  "memory_notes": [
    {
      "id": "london_continuation",
      "kind": "standing_rule",
      "text": "Prefer London continuation after early impulse",
      "bias": "long",
      "keywords": ["london", "continuation"],
      "priority": 1
    },
    {
      "id": "late_ny_fade",
      "kind": "anti_rule",
      "text": "Avoid late-NY fade entries",
      "bias": null,
      "keywords": ["ny", "fade"],
      "priority": 2
    }
  ]
}
```

Rules for JSON:
- kind must be standing_rule, anti_rule, lesson, or note.
- Prefer rule text that names the instrument condition / session / signal reason.
- Do NOT include EMA/filter suggestion paths.
- Do NOT write rules whose only claim is "more trades" or "higher P&L".
- Do NOT encode the window's total return or claim prior knowledge of this exact period.
- Keep the list short (≤8 notes). Be grounded in the supplied data.
"""

_MEMORY_FEEDBACK_SYSTEM_PROMPT = f"""\
You are BrokerAI's AI Strategy learning coach reviewing a compiled-playbook
*signal review* over an instrument's historical candles.

Your job is to improve the strategy's *memory digest* (standing rules and anti-rules)
so future compiles know *where on the instrument* to lean long/short or stand aside.
This is NOT an EMA/filter builder review. Do not suggest builder param paths.
Do NOT judge success by trade count, win rate, or realized P&L. Zero fills is normal
and is not failure by itself.

Anti-cheat: Treat this candle walk as a fresh pass. Do NOT encode the window's total
return into standing rules.

Use rigorous reasoning:
1. Describe the instrument trend from `period_summary`, `trend_segments`, and
   `playbook_review` (direction of travel, ranges, regime shifts).
2. For sampled bars in `should_have_traded` / `stood_aside`, explain:
   "We should have traded here based on {{signal}}" or
   "Stand aside here because {{reason}}".
3. Judge whether the compiled bias + momentum gate *aligned with the instrument*
   — not whether the simulator filled many tickets.
4. Propose durable standing rules (where/when the book should lean in) and
   anti-rules (where it should refuse). Prefer location/session/regime language.
5. Call out overfitting: prefer generalizable lessons over fitting a few bars.

Respond in clear markdown with these sections:
## Instrument trend
## Where we should have traded
## Where we should have stood aside
## Memory lessons
## Risks / caveats

{_MEMORY_NOTES_JSON_FOOTER}"""

_EXPLORE_FEEDBACK_SYSTEM_PROMPT = f"""\
You are BrokerAI's AI Strategy learning coach on an *explore* (pattern-only) pass.

This run walked candles and emitted signals but did **not** execute fills. Distill
durable pattern / structure lessons into the memory digest (standing rules and
anti-rules) for later trade loops.

Do NOT invent trade outcomes, P&L, win rates, or fill counts. Do NOT suggest builder
param paths. Do NOT encode the window's total return as a standing rule.

Anti-cheat: Write rules as if the next loop has never seen this exact series — only
your distilled lessons carry forward.

Use rigorous reasoning:
1. From `period_summary`, `trend_segments`, and `playbook_review`, describe regimes,
   ranges, and directional structure (sessions, HTF bias, momentum context).
2. For `should_have_traded` / `stood_aside` samples, explain pattern-level reasons —
   not hypothetical tickets.
3. Propose standing rules (where to lean) and anti-rules (where to refuse) in
   location/session/regime language.
4. Prefer generalizable lessons; call out overfitting.

Respond in clear markdown with these sections:
## Instrument patterns
## Promising locations
## Stand-aside locations
## Memory lessons
## Risks / caveats

{_MEMORY_NOTES_JSON_FOOTER}"""

_TRADE_MEMORY_FEEDBACK_SYSTEM_PROMPT = f"""\
You are BrokerAI's AI Strategy learning coach reviewing a *live-parity trade* pass.

This run executed fills as if the data were live. Learn only from *this run's*
entries, exits, signals, and filter fails — plus prior digest rules already in
`params_snapshot`. Treat the candle series as new: you do not "remember" walking
this same window before, even if startup previously explored it.

Do NOT judge success by trade count alone. Do NOT encode the window's total return
into standing rules. Do NOT suggest builder param paths.

Use rigorous reasoning:
1. Relate this run's fills and signals to instrument structure
   (`period_summary`, `trend_segments`, `playbook_review`).
2. For good/bad outcomes, explain "traded here based on {{signal}}" or
   "should have stood aside because {{reason}}".
3. Update standing / anti rules so the next compile improves decisions without
   memorizing this period's path.
4. Call out overfitting.

Respond in clear markdown with these sections:
## Instrument trend
## Trade outcomes
## Where we should have stood aside
## Memory lessons
## Risks / caveats

{_MEMORY_NOTES_JSON_FOOTER}"""

PLAYBOOK_REVIEW_MAX_EVALS = 400
PLAYBOOK_REVIEW_SAMPLE_LIMIT = 24
TREND_SEGMENT_COUNT = 4

# Prevent overlapping auto/manual jobs for the same run on one API process.
_inflight_feedback: set[str] = set()


def resolve_feedback_loop_mode(run: dict[str, Any] | None) -> str | None:
    """Return ``explore`` / ``trade`` when set on a startup run, else ``None``."""
    if not isinstance(run, dict):
        return None
    mode = str(run.get("loop_mode") or "").strip().lower()
    if mode in {"explore", "trade"}:
        return mode
    return None


def scrub_period_spoilers(context: dict[str, Any]) -> dict[str, Any]:
    """Drop full-window return spoilers so lessons cannot encode period P&L."""
    out = dict(context)
    summary = out.get("period_summary")
    if isinstance(summary, dict):
        out["period_summary"] = {k: v for k, v in summary.items() if k != "period_return"}
    return out


def shape_context_for_loop_mode(
    context: dict[str, Any],
    *,
    loop_mode: str | None,
) -> dict[str, Any]:
    """Package feedback context for explore vs trade (anti-cheat).

    Explore drops fill/equity/stats so the coach cannot invent trade outcomes.
    Both modes scrub ``period_return`` so digests cannot memorize window P&L.
    """
    shaped = scrub_period_spoilers(context)
    mode = (loop_mode or "").strip().lower() or None
    if mode == "explore":
        shaped["trades"] = []
        shaped["equity_curve"] = []
        shaped["stats"] = {
            "total_trades": 0,
            "note": "explore_loop: fills disabled; ignore trade metrics",
        }
        shaped["candle_windows"] = []
        shaped["framing"] = (
            "explore_patterns: signal-only pass; distill structure lessons; "
            "no fills; no period-return spoilers; next loop has not seen this series"
        )
        if isinstance(shaped.get("run"), dict):
            shaped["run"] = {**shaped["run"], "loop_mode": "explore"}
        return shaped
    if mode == "trade":
        shaped["framing"] = (
            "live_parity_trade: learn from this run's fills/signals only; "
            "treat candles as unseen; no period-return spoilers; prior lessons "
            "live only in digest/params_snapshot"
        )
        if isinstance(shaped.get("run"), dict):
            shaped["run"] = {**shaped["run"], "loop_mode": "trade"}
        return shaped
    # Daily / unspecified memory reviews: still scrub period_return.
    if shaped.get("playbook_review") is not None and "framing" not in shaped:
        shaped["framing"] = (
            "signal_review: judge instrument trend alignment and where the playbook "
            "should have traded or stood aside; ignore trade count / P&L as success "
            "metrics; do not encode period_return"
        )
    return shaped


def is_ai_strategy_daily_run(run: dict[str, Any] | None) -> bool:
    """True when the backtest should use memory-oriented AI feedback.

    Covers daily cadence runs and create-time startup improve loops.
    """
    if not isinstance(run, dict):
        return False
    origin = str(run.get("origin") or "")
    if origin == ORIGIN_AI_STRATEGY_DAILY:
        return True
    # Late import avoids circular import with startup → ai_feedback.
    from brokerai.ai_strategy.startup import ORIGIN_AI_STRATEGY_STARTUP

    return origin == ORIGIN_AI_STRATEGY_STARTUP


def normalize_memory_notes(raw: Any) -> list[dict[str, Any]]:
    """Sanitize memory-oriented feedback notes (daily AI Strategy runs)."""
    if not isinstance(raw, list):
        return []
    allowed_kinds = {"standing_rule", "anti_rule", "lesson", "note"}
    allowed_bias = {"long", "short", "flat", "both"}
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        kind = str(item.get("kind") or "lesson").strip().lower()
        if kind not in allowed_kinds:
            kind = "lesson"
        bias_raw = item.get("bias")
        bias: str | None
        if isinstance(bias_raw, str) and bias_raw.strip() in allowed_bias:
            bias = bias_raw.strip()
        else:
            bias = None
        keywords_raw = item.get("keywords") or []
        keywords: list[str] = []
        if isinstance(keywords_raw, list):
            for token in keywords_raw:
                cleaned = str(token).strip().lower()
                if cleaned and cleaned not in keywords:
                    keywords.append(cleaned)
        note_id = str(item.get("id") or "").strip() or f"note-{len(out) + 1}"
        try:
            priority = int(item.get("priority") or 0)
        except (TypeError, ValueError):
            priority = 0
        out.append(
            {
                "id": note_id,
                "kind": kind,
                "text": text,
                "bias": bias,
                "keywords": keywords,
                "priority": priority,
            }
        )
        if len(out) >= 12:
            break
    return out


def parse_memory_notes_from_markdown(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Extract a ``memory_notes`` JSON fence; return cleaned markdown + notes."""
    import re

    if not text:
        return "", []
    pattern = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.MULTILINE)
    cleaned = text
    notes: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict) or "memory_notes" not in parsed:
            continue
        notes = normalize_memory_notes(parsed.get("memory_notes"))
        cleaned = (text[: match.start()] + text[match.end() :]).strip()
        break
    return cleaned, notes


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_instant(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def empty_ai_feedback() -> dict[str, Any]:
    return {
        "status": None,
        "model_id": None,
        "model_name": None,
        "reasoning_effort": None,
        "markdown": None,
        "suggestions": [],
        "memory_notes": [],
        "error": None,
        "started_at": None,
        "finished_at": None,
        "usage": None,
    }


def normalize_ai_feedback(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize stored feedback; return ``None`` when never requested."""
    if not raw or not isinstance(raw, dict):
        return None
    status = raw.get("status")
    if status is None and not raw.get("markdown") and not raw.get("error"):
        return None
    if isinstance(status, str) and status.strip() in AI_FEEDBACK_STATUSES:
        normalized_status = status.strip()
    elif raw.get("markdown"):
        normalized_status = AI_FEEDBACK_STATUS_COMPLETED
    elif raw.get("error"):
        normalized_status = AI_FEEDBACK_STATUS_FAILED
    else:
        normalized_status = AI_FEEDBACK_STATUS_QUEUED
    effort = raw.get("reasoning_effort")
    if not isinstance(effort, str) or effort not in REASONING_EFFORT_OPTIONS:
        effort = None
    return {
        "status": normalized_status,
        "model_id": str(raw["model_id"]) if raw.get("model_id") else None,
        "model_name": str(raw["model_name"]) if raw.get("model_name") else None,
        "reasoning_effort": effort,
        "markdown": str(raw["markdown"]) if raw.get("markdown") is not None else None,
        "suggestions": normalize_suggestions(raw.get("suggestions") or []),
        "memory_notes": normalize_memory_notes(raw.get("memory_notes") or []),
        "error": str(raw["error"]) if raw.get("error") is not None else None,
        "started_at": str(raw["started_at"]) if raw.get("started_at") else None,
        "finished_at": str(raw["finished_at"]) if raw.get("finished_at") else None,
        "usage": dict(raw["usage"]) if isinstance(raw.get("usage"), dict) else None,
    }


def downsample_equity_for_feedback(
    curve: list[dict[str, Any]],
    *,
    max_points: int = EQUITY_FEEDBACK_MAX_POINTS,
) -> list[dict[str, Any]]:
    """Downsample equity for the LLM prompt; keep endpoints and local extrema."""
    if len(curve) <= max_points:
        return [
            {"time": p.get("time"), "equity": float(p.get("equity") or 0)}
            for p in curve
        ]
    if max_points < 2:
        last = curve[-1]
        return [{"time": last.get("time"), "equity": float(last.get("equity") or 0)}]

    indexes: set[int] = {0, len(curve) - 1}
    # Uniform grid
    step = (len(curve) - 1) / (max_points - 1)
    for i in range(max_points):
        indexes.add(int(round(i * step)))

    # Local peaks / troughs (light pass)
    for i in range(1, len(curve) - 1):
        prev_e = float(curve[i - 1].get("equity") or 0)
        cur_e = float(curve[i].get("equity") or 0)
        next_e = float(curve[i + 1].get("equity") or 0)
        if (cur_e >= prev_e and cur_e >= next_e) or (cur_e <= prev_e and cur_e <= next_e):
            indexes.add(i)

    chosen = sorted(indexes)
    if len(chosen) > max_points:
        # Prefer endpoints + evenly spaced among extrema+grid
        mid = chosen[1:-1]
        keep = max_points - 2
        if keep <= 0:
            chosen = [chosen[0], chosen[-1]]
        else:
            stride = max(1, len(mid) // keep)
            sampled = mid[::stride][:keep]
            chosen = [chosen[0], *sampled, chosen[-1]]

    return [
        {"time": curve[i].get("time"), "equity": float(curve[i].get("equity") or 0)}
        for i in chosen
    ]


def reconstruct_trades_from_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair entry actions with the next exit/sl/tp into closed trades.

    Edge cases:
    - Orphan exits (no open entry) are skipped.
    - Open entry with no exit is omitted (incomplete trade).
    - Only one flat position is assumed (backtest simulator is single-position).
    """
    trades: list[dict[str, Any]] = []
    open_entry: dict[str, Any] | None = None

    for action in sorted(actions, key=lambda a: int(a.get("sequence") or 0)):
        kind = str(action.get("kind") or "")
        meta = action.get("meta") if isinstance(action.get("meta"), dict) else {}
        if kind == "entry":
            open_entry = {
                "entry_sequence": action.get("sequence"),
                "entry_time": action.get("bar_time"),
                "direction": meta.get("direction"),
                "entry_price": meta.get("price"),
                "units": meta.get("units"),
                "entry_message": action.get("message"),
            }
            continue
        if kind in EXIT_KINDS and open_entry is not None:
            pnl = meta.get("realized_pnl")
            try:
                pnl_f = float(pnl) if pnl is not None else None
            except (TypeError, ValueError):
                pnl_f = None
            trades.append(
                {
                    **open_entry,
                    "exit_sequence": action.get("sequence"),
                    "exit_time": action.get("bar_time"),
                    "exit_kind": kind,
                    "exit_reason": meta.get("reason"),
                    "exit_price": meta.get("price"),
                    "realized_pnl": pnl_f,
                    "exit_message": action.get("message"),
                }
            )
            open_entry = None
    return trades


def _sample_by_kind(
    actions: list[dict[str, Any]],
    *,
    kind: str,
    limit: int,
    prefer_near_loss_times: set[str] | None = None,
) -> list[dict[str, Any]]:
    matching = [a for a in actions if str(a.get("kind") or "") == kind]
    if len(matching) <= limit:
        return [
            {
                "sequence": a.get("sequence"),
                "kind": a.get("kind"),
                "message": a.get("message"),
                "bar_time": a.get("bar_time"),
                "meta": a.get("meta"),
            }
            for a in matching
        ]

    prefer = prefer_near_loss_times or set()

    def score(action: dict[str, Any]) -> tuple[int, int]:
        bar = str(action.get("bar_time") or "")
        near_loss = 0 if bar and bar in prefer else 1
        return (near_loss, int(action.get("sequence") or 0))

    ranked = sorted(matching, key=score)
    chosen = ranked[:limit]
    chosen.sort(key=lambda a: int(a.get("sequence") or 0))
    return [
        {
            "sequence": a.get("sequence"),
            "kind": a.get("kind"),
            "message": a.get("message"),
            "bar_time": a.get("bar_time"),
            "meta": a.get("meta"),
        }
        for a in chosen
    ]


def summarize_period_candles(candles: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate OHLC stats for the evaluation window (no full series)."""
    if not candles:
        return None
    try:
        first_open = float(candles[0]["open"])
        last_close = float(candles[-1]["close"])
        high = max(float(c["high"]) for c in candles)
        low = min(float(c["low"]) for c in candles)
    except (KeyError, TypeError, ValueError):
        return None
    ranges: list[float] = []
    for c in candles:
        try:
            ranges.append(float(c["high"]) - float(c["low"]))
        except (KeyError, TypeError, ValueError):
            continue
    avg_range = sum(ranges) / len(ranges) if ranges else None
    period_return = (last_close - first_open) / first_open if first_open else None
    return {
        "bar_count": len(candles),
        "first_time": candles[0].get("time"),
        "last_time": candles[-1].get("time"),
        "open": first_open,
        "high": high,
        "low": low,
        "close": last_close,
        "period_return": period_return,
        "avg_bar_range": avg_range,
    }


def build_trend_segments(
    candles: list[dict[str, Any]],
    *,
    segments: int = TREND_SEGMENT_COUNT,
) -> list[dict[str, Any]]:
    """Split the window into coarse trend segments (open→close return each)."""
    if not candles or segments < 1:
        return []
    n = len(candles)
    out: list[dict[str, Any]] = []
    for i in range(segments):
        start = (i * n) // segments
        end = ((i + 1) * n) // segments
        if end <= start:
            continue
        chunk = candles[start:end]
        try:
            open_px = float(chunk[0]["open"])
            close_px = float(chunk[-1]["close"])
            high = max(float(c["high"]) for c in chunk)
            low = min(float(c["low"]) for c in chunk)
        except (KeyError, TypeError, ValueError):
            continue
        ret = (close_px - open_px) / open_px if open_px else None
        direction = "up" if ret is not None and ret > 0 else "down" if ret is not None and ret < 0 else "flat"
        out.append(
            {
                "index": i,
                "bar_count": len(chunk),
                "first_time": chunk[0].get("time"),
                "last_time": chunk[-1].get("time"),
                "open": open_px,
                "high": high,
                "low": low,
                "close": close_px,
                "return": ret,
                "direction": direction,
            }
        )
    return out


def _is_compiled_playbook_params(params: Any) -> bool:
    if not isinstance(params, dict):
        return False
    signal = params.get("signal")
    if not isinstance(signal, dict):
        return False
    return str(signal.get("type") or "") == "compiled_playbook"


def build_playbook_signal_review(
    candles: list[dict[str, Any]],
    params: dict[str, Any],
    *,
    max_evals: int = PLAYBOOK_REVIEW_MAX_EVALS,
    sample_limit: int = PLAYBOOK_REVIEW_SAMPLE_LIMIT,
) -> dict[str, Any] | None:
    """Re-evaluate playbook gates across the period for signal-lesson context.

    Samples bars (stride) so long histories stay cheap. Returns counts by gate
    reason plus concrete ``should_have_traded`` / ``stood_aside`` examples the
    LLM can cite — independent of whether the simulator filled tickets.
    """
    if not candles or not _is_compiled_playbook_params(params):
        return None

    from brokerai.strategies.candles import effective_min_candles
    from brokerai.trading.indicator_cache import IndicatorCacheView
    from brokerai.trading.presets.compiled_playbook.signal import (
        CompiledPlaybookSignalEvaluator,
    )

    signal = params.get("signal") if isinstance(params.get("signal"), dict) else {}
    min_required = max(1, int(effective_min_candles(params) or 1))
    if len(candles) < min_required + 1:
        return {
            "bias": signal.get("bias"),
            "standing_rules": list(signal.get("standing_rules") or [])[:12],
            "anti_rules": list(signal.get("anti_rules") or [])[:12],
            "anti_active": bool(signal.get("anti_active")),
            "require_momentum": bool(signal.get("require_momentum", True)),
            "momentum_bars": signal.get("momentum_bars"),
            "eval_count": 0,
            "reason_counts": {},
            "should_have_traded": [],
            "stood_aside": [],
            "note": "Not enough candles to re-evaluate playbook gates",
        }

    evaluator = CompiledPlaybookSignalEvaluator()
    indicators = IndicatorCacheView(pair="review", timeframe=str(params.get("timeframe") or "M15"))
    usable = len(candles) - min_required + 1
    stride = max(1, (usable + max_evals - 1) // max_evals)
    reason_counts: dict[str, int] = {}
    should_trade: list[dict[str, Any]] = []
    stood_aside: list[dict[str, Any]] = []
    eval_count = 0
    fire_count = 0

    for end_idx in range(min_required, len(candles) + 1, stride):
        window = candles[:end_idx]
        result = evaluator.evaluate(window, params, indicators)
        eval_count += 1
        meta = result.metadata if isinstance(result.metadata, dict) else {}
        if result.direction:
            fire_count += 1
            reason = str(meta.get("signal") or f"playbook_{result.direction}")
        else:
            reason = str(meta.get("reason") or "no_signal")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        bar = window[-1]
        try:
            close_px = float(bar["close"])
        except (KeyError, TypeError, ValueError):
            close_px = None
        sample = {
            "time": bar.get("time"),
            "close": close_px,
            "bias": meta.get("bias") or signal.get("bias"),
            "momentum": meta.get("momentum"),
            "signal": meta.get("signal"),
            "reason": reason,
            "direction": result.direction,
            "lesson": (
                f"Should have traded {result.direction} based on {meta.get('signal') or reason}"
                if result.direction
                else f"Stand aside because {reason}"
            ),
        }
        if result.direction and len(should_trade) < sample_limit:
            should_trade.append(sample)
        elif not result.direction and len(stood_aside) < sample_limit:
            if reason not in {"insufficient_candles"}:
                stood_aside.append(sample)

    return {
        "bias": signal.get("bias"),
        "standing_rules": list(signal.get("standing_rules") or [])[:12],
        "anti_rules": list(signal.get("anti_rules") or [])[:12],
        "anti_active": bool(signal.get("anti_active")),
        "require_momentum": bool(signal.get("require_momentum", True)),
        "momentum_bars": signal.get("momentum_bars"),
        "digest_summary": signal.get("digest_summary") or "",
        "eval_count": eval_count,
        "eval_stride": stride,
        "reason_counts": reason_counts,
        "signal_fire_count": fire_count,
        "signal_fire_rate": round(fire_count / eval_count, 4) if eval_count else 0.0,
        "should_have_traded": should_trade,
        "stood_aside": stood_aside,
        "trend_segments": build_trend_segments(candles),
    }


def _compact_candle(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "t": c.get("time"),
        "o": c.get("open"),
        "h": c.get("high"),
        "l": c.get("low"),
        "c": c.get("close"),
    }


def slice_candle_windows(
    candles: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    *,
    timeframe: str,
    window_bars: int = CANDLE_WINDOW_BARS,
    max_windows: int = MAX_TRADE_WINDOWS,
) -> list[dict[str, Any]]:
    """Extract ±N bars around each trade's entry and exit.

    Prefer losing trades when capping windows. Candles must be sorted ascending
    by time. Missing bars around a trade yield an empty ``bars`` list for that
    window rather than failing the whole package.
    """
    if not candles or not trades:
        return []

    index_by_time: dict[str, int] = {}
    for i, c in enumerate(candles):
        t = str(c.get("time") or "")
        if t:
            index_by_time[t] = i

    try:
        bar_delta = timeframe_to_duration(timeframe)
    except Exception:
        bar_delta = timedelta(minutes=15)

    # Prefer losses first, then chronological
    ordered = sorted(
        trades,
        key=lambda t: (
            0 if (t.get("realized_pnl") is not None and float(t["realized_pnl"]) < 0) else 1,
            int(t.get("entry_sequence") or 0),
        ),
    )[:max_windows]

    windows: list[dict[str, Any]] = []
    for trade in ordered:
        for label, time_key in (("entry", "entry_time"), ("exit", "exit_time")):
            raw_t = trade.get(time_key)
            if not raw_t:
                continue
            t_str = str(raw_t)
            idx = index_by_time.get(t_str)
            if idx is None:
                # Nearest bar by parsed time
                target = _parse_instant(raw_t)
                if target is None:
                    continue
                best_i = None
                best_dist = None
                for i, c in enumerate(candles):
                    ct = _parse_instant(c.get("time"))
                    if ct is None:
                        continue
                    dist = abs((ct - target).total_seconds())
                    if best_dist is None or dist < best_dist:
                        best_dist = dist
                        best_i = i
                if best_i is None or (best_dist is not None and best_dist > bar_delta.total_seconds() * 2):
                    continue
                idx = best_i
            start = max(0, idx - window_bars)
            end = min(len(candles), idx + window_bars + 1)
            windows.append(
                {
                    "trade_entry_sequence": trade.get("entry_sequence"),
                    "around": label,
                    "anchor_time": candles[idx].get("time"),
                    "bars": [_compact_candle(c) for c in candles[start:end]],
                }
            )
    return windows


def build_backtest_feedback_messages(
    context: dict[str, Any],
    *,
    memory_oriented: bool = False,
    loop_mode: str | None = None,
) -> list[dict[str, str]]:
    """Build chat messages for strategy-feedback analysis.

    When ``memory_oriented`` is True (AI Strategy daily/startup origin), use the
    memory digest prompt/schema instead of EMA builder SUGGESTION_ALLOWLIST.
    ``loop_mode`` selects explore vs trade prompts for startup loops.
    """
    payload = json.dumps(context, default=str, separators=(",", ":"))
    if len(payload) > MAX_CONTEXT_JSON_CHARS:
        # Drop candle windows first, then dense samples, to stay in budget.
        slim = dict(context)
        slim["candle_windows"] = []
        slim["equity_curve"] = []
        slim["note"] = (
            "Candle windows/equity omitted because context exceeded the size budget; "
            "rely on playbook_review, period_summary, and trend_segments."
            if memory_oriented
            else (
                "Candle windows omitted because context exceeded the size budget; "
                "rely on trades, stats, and period_summary."
            )
        )
        payload = json.dumps(slim, default=str, separators=(",", ":"))
        if len(payload) > MAX_CONTEXT_JSON_CHARS:
            slim["signals_sample"] = slim.get("signals_sample", [])[:10]
            slim["filter_fails_sample"] = slim.get("filter_fails_sample", [])[:10]
            slim["trades"] = slim.get("trades", [])[:10]
            review = slim.get("playbook_review")
            if isinstance(review, dict):
                slim["playbook_review"] = {
                    **review,
                    "should_have_traded": list(review.get("should_have_traded") or [])[:12],
                    "stood_aside": list(review.get("stood_aside") or [])[:12],
                }
            payload = json.dumps(slim, default=str, separators=(",", ":"))

    mode = (loop_mode or "").strip().lower() or None
    if memory_oriented and mode == "explore":
        user = (
            "Review this AI Strategy *explore* (pattern-only) pass. Focus on "
            "instrument structure and where the book should lean or stand aside — "
            "not fills or P&L. Propose memory digest standing/anti rules. Data "
            "follows as JSON.\n\n"
            f"```json\n{payload}\n```"
        )
        system = _EXPLORE_FEEDBACK_SYSTEM_PROMPT
    elif memory_oriented and mode == "trade":
        user = (
            "Review this AI Strategy *live-parity trade* pass. Learn from this "
            "run's outcomes only; treat candles as unseen. Propose memory digest "
            "standing/anti rules. Do not encode period return. Data follows as "
            "JSON.\n\n"
            f"```json\n{payload}\n```"
        )
        system = _TRADE_MEMORY_FEEDBACK_SYSTEM_PROMPT
    elif memory_oriented:
        user = (
            "Review this AI Strategy playbook signal pass over the instrument. "
            "Focus on trend location and where the book should have traded or stood "
            "aside based on signals/reasons — not trade count or P&L. Propose memory "
            "digest standing/anti rules. Do not suggest builder param paths. "
            "Data follows as JSON.\n\n"
            f"```json\n{payload}\n```"
        )
        system = _MEMORY_FEEDBACK_SYSTEM_PROMPT
    else:
        user = (
            "Analyze this completed BrokerAI backtest and suggest where the strategy "
            "could be improved. Data follows as JSON.\n\n"
            f"```json\n{payload}\n```"
        )
        system = _FEEDBACK_SYSTEM_PROMPT
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def apply_memory_feedback_to_digest(
    strategy_id: str,
    memory_notes: list[dict[str, Any]],
    *,
    source: str = "ai_strategy_daily_feedback",
) -> dict[str, Any] | None:
    """Persist memory notes into a new digest version (not EMA params).

    Does **not** call ``apply_suggestions_to_params``. When notes are empty,
    queues a learning job instead so Slice 3 can refresh from outcomes.
    """
    sid = (strategy_id or "").strip()
    if not sid:
        return None
    digests = StrategyMemoryDigestsRepository()
    if not memory_notes:
        return await queue_learning_job(sid, force=True)

    prior = await digests.get_latest(sid)
    merged = merge_feedback_notes_into_digest(
        prior, memory_notes, strategy_id=sid, source=source
    )
    version = await digests.next_version(sid)
    return await digests.create_version(sid, merged, version=version)


async def build_backtest_feedback_context(run_id: str) -> dict[str, Any]:
    """Load run + actions + logs + candle windows into a compact analysis package."""
    runs_repo = BacktestRunsRepository()
    run = await runs_repo.get_by_id(run_id)
    if run is None:
        raise ValueError(f"Backtest run not found: {run_id}")

    actions = await BacktestActionsRepository().list_for_run(run_id, limit=10_000)
    trades = reconstruct_trades_from_actions(actions)

    loss_times: set[str] = set()
    for trade in trades:
        if trade.get("realized_pnl") is not None and float(trade["realized_pnl"]) < 0:
            if trade.get("entry_time"):
                loss_times.add(str(trade["entry_time"]))
            if trade.get("exit_time"):
                loss_times.add(str(trade["exit_time"]))

    signals = _sample_by_kind(
        actions,
        kind="signal",
        limit=SIGNAL_SAMPLE_LIMIT,
        prefer_near_loss_times=loss_times,
    )
    filter_fails = _sample_by_kind(
        actions,
        kind="filter_fail",
        limit=FILTER_FAIL_SAMPLE_LIMIT,
        prefer_near_loss_times=loss_times,
    )

    logs = await BacktestLogsRepository().list_for_run(run_id, limit=2000)
    warn_logs = [
        {"level": e.get("level"), "message": e.get("message"), "created_at": e.get("created_at")}
        for e in logs
        if str(e.get("level") or "").upper() in {"WARNING", "WARN", "ERROR"}
    ][:MAX_WARN_LOGS]

    symbol = str(run.get("instrument") or (run.get("instruments") or [None])[0] or "")
    timeframe = str(run.get("timeframe") or "M15")
    since = run.get("period_start")
    until = run.get("period_end")

    candles: list[dict[str, Any]] = []
    period_summary: dict[str, Any] | None = None
    trend_segments: list[dict[str, Any]] = []
    candle_windows: list[dict[str, Any]] = []
    playbook_review: dict[str, Any] | None = None
    params_snapshot = run.get("params_snapshot") if isinstance(run.get("params_snapshot"), dict) else {}
    if symbol and since and until:
        try:
            candles = await CandleCache().read_candles(
                symbol,
                timeframe,
                source=OANDA_SOURCE,
                since=str(since),
                until=str(until),
            )
            period_summary = summarize_period_candles(candles)
            trend_segments = build_trend_segments(candles)
            candle_windows = slice_candle_windows(
                candles,
                trades,
                timeframe=timeframe,
            )
            if _is_compiled_playbook_params(params_snapshot):
                playbook_review = build_playbook_signal_review(candles, params_snapshot)
        except Exception:
            logger.warning(
                "Failed to load candles for AI feedback on run %s", run_id, exc_info=True
            )

    equity = downsample_equity_for_feedback(list(run.get("equity_curve") or []))

    # For playbook/AI Strategy reviews, keep stats available but de-emphasize them
    # in the package shape the prompt sees first.
    context: dict[str, Any] = {
        "run": {
            "id": run.get("id"),
            "name": run.get("name"),
            "strategy_id": run.get("strategy_id"),
            "strategy_name": run.get("strategy_name"),
            "asset_class": run.get("asset_class"),
            "instrument": symbol,
            "timeframe": timeframe,
            "period": run.get("period"),
            "period_start": run.get("period_start"),
            "period_end": run.get("period_end"),
            "account_margin": run.get("account_margin"),
            "created_at": run.get("created_at"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
        },
        "params_snapshot": params_snapshot or run.get("params_snapshot"),
        "period_summary": period_summary,
        "trend_segments": trend_segments,
        "playbook_review": playbook_review,
        "signals_sample": signals,
        "filter_fails_sample": filter_fails,
        "candle_windows": candle_windows,
        "warn_logs": warn_logs,
        "stats": run.get("stats"),
        "trades": trades,
        "equity_curve": equity,
    }
    if playbook_review is not None:
        context["framing"] = (
            "signal_review: judge instrument trend alignment and where the playbook "
            "should have traded or stood aside; ignore trade count / P&L as success metrics"
        )
    return context


async def mark_ai_feedback_running(
    run_id: str,
    *,
    model_id: str,
    model_name: str,
    reasoning_effort: str,
) -> dict[str, Any] | None:
    """Persist running status before the LLM call. Returns serialized run."""
    feedback = {
        "status": AI_FEEDBACK_STATUS_RUNNING,
        "model_id": model_id,
        "model_name": model_name,
        "reasoning_effort": reasoning_effort,
        "markdown": None,
        "suggestions": [],
        "memory_notes": [],
        "error": None,
        "started_at": _now_iso(),
        "finished_at": None,
        "usage": None,
    }
    return await BacktestRunsRepository().update_ai_feedback(run_id, feedback)


async def run_backtest_ai_feedback(run_id: str) -> dict[str, Any]:
    """Build context, call the configured model, and persist ``ai_feedback``.

    Returns the serialized run document. LLM and packaging failures are written
    to ``ai_feedback`` rather than raised. Misconfiguration before the running
    marker is raised to the caller.
    """
    runs_repo = BacktestRunsRepository()
    settings = await BacktestSettingsRepository().get()
    if not settings.get("ai_feedback_enabled"):
        raise RuntimeError("AI feedback is disabled in backtest settings")

    model_id = settings.get("ai_feedback_model_id")
    model_name = settings.get("ai_feedback_model_name")
    effort = settings.get("ai_feedback_reasoning_effort") or "medium"
    if not model_id or not model_name:
        raise RuntimeError("No AI feedback model configured in backtest settings")

    source = await AiModelsRepository().find_enabled_by_id(str(model_id))
    if source is None:
        raise RuntimeError("Configured AI feedback model source is missing or disabled")

    bound = bind_source_model(source, str(model_name))
    model_type = str(bound.get("type") or "")
    base_url = str(bound.get("base_url") or "")
    api_key = bound.get("api_key") or None
    resolved_name = str(bound.get("model_name") or model_name)

    started_at = _now_iso()
    await mark_ai_feedback_running(
        run_id,
        model_id=str(model_id),
        model_name=resolved_name,
        reasoning_effort=str(effort),
    )

    try:
        # Prefer raw doc so origin / cadence / loop_mode metadata is available.
        run_doc = await runs_repo.get_raw_doc(run_id) or await runs_repo.get_by_id(run_id)
        memory_oriented = is_ai_strategy_daily_run(run_doc)
        loop_mode = resolve_feedback_loop_mode(run_doc) if memory_oriented else None
        context = await build_backtest_feedback_context(run_id)
        if isinstance(run_doc, dict):
            context.setdefault("run", {})
            if isinstance(context["run"], dict):
                context["run"]["origin"] = run_doc.get("origin")
                context["run"]["cadence_key"] = run_doc.get("cadence_key")
                context["run"]["digest_version"] = run_doc.get("digest_version")
                if loop_mode:
                    context["run"]["loop_mode"] = loop_mode
        if memory_oriented:
            context = shape_context_for_loop_mode(context, loop_mode=loop_mode)
        messages = build_backtest_feedback_messages(
            context, memory_oriented=memory_oriented, loop_mode=loop_mode
        )
        markdown = await analyze_with_model(
            model_type,
            base_url,
            resolved_name,
            messages,
            api_key if isinstance(api_key, str) else None,
            reasoning_effort=None if effort == "none" else str(effort),
            cost_context={
                "operation": (
                    "ai_strategy_explore_feedback"
                    if loop_mode == "explore"
                    else (
                        "ai_strategy_trade_feedback"
                        if loop_mode == "trade"
                        else (
                            "ai_strategy_daily_feedback"
                            if memory_oriented
                            else "backtest_ai_feedback"
                        )
                    )
                ),
                "backtest_run_id": run_id,
                "strategy_id": str((run_doc or {}).get("strategy_id") or ""),
            },
        )
        if memory_oriented:
            # Memory fork: never parse/apply EMA SUGGESTION_ALLOWLIST paths.
            cleaned_markdown, memory_notes = parse_memory_notes_from_markdown(markdown)
            suggestions: list[dict[str, Any]] = []
            strategy_id = str((run_doc or {}).get("strategy_id") or "")
            digest_source = (
                "ai_strategy_startup_explore"
                if loop_mode == "explore"
                else (
                    "ai_strategy_startup_trade"
                    if loop_mode == "trade"
                    else "ai_strategy_daily_feedback"
                )
            )
            try:
                await apply_memory_feedback_to_digest(
                    strategy_id, memory_notes, source=digest_source
                )
            except Exception:
                logger.exception(
                    "Failed to apply memory feedback for daily run %s strategy=%s",
                    run_id,
                    strategy_id,
                )
        else:
            params_snapshot = (
                context.get("params_snapshot")
                if isinstance(context.get("params_snapshot"), dict)
                else None
            )
            cleaned_markdown, suggestions = parse_suggestions_from_markdown(
                markdown,
                params_snapshot=params_snapshot,
            )
            memory_notes = []
        feedback = {
            "status": AI_FEEDBACK_STATUS_COMPLETED,
            "model_id": str(model_id),
            "model_name": resolved_name,
            "reasoning_effort": str(effort),
            "markdown": cleaned_markdown,
            "suggestions": suggestions,
            "memory_notes": memory_notes,
            "error": None,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "usage": None,
        }
        updated = await runs_repo.update_ai_feedback(run_id, feedback)
        return updated or {"id": run_id, "ai_feedback": normalize_ai_feedback(feedback)}
    except Exception as exc:
        logger.exception("AI feedback failed for run %s", run_id)
        feedback = {
            "status": AI_FEEDBACK_STATUS_FAILED,
            "model_id": str(model_id),
            "model_name": resolved_name,
            "reasoning_effort": str(effort),
            "markdown": None,
            "suggestions": [],
            "memory_notes": [],
            "error": str(exc),
            "started_at": started_at,
            "finished_at": _now_iso(),
            "usage": None,
        }
        updated = await runs_repo.update_ai_feedback(run_id, feedback)
        return updated or {"id": run_id, "ai_feedback": normalize_ai_feedback(feedback)}
    finally:
        _inflight_feedback.discard(run_id)


def ai_feedback_settings_ready(settings: dict[str, Any]) -> bool:
    """True when master toggle is on and a model is selected."""
    if not settings.get("ai_feedback_enabled"):
        return False
    model_id = settings.get("ai_feedback_model_id")
    model_name = settings.get("ai_feedback_model_name")
    return bool(model_id and model_name)


async def begin_ai_feedback_job(run_id: str) -> dict[str, Any]:
    """Validate + mark running, then schedule the background LLM job.

    Idempotent while already ``running``: returns the current run without
    starting a second task. Re-runs are allowed after completed/failed.
    """
    runs_repo = BacktestRunsRepository()
    run = await runs_repo.get_by_id(run_id)
    if run is None:
        raise ValueError("Backtest run not found")
    if run.get("status") != BACKTEST_RUN_STATUS_COMPLETED:
        raise ValueError("AI feedback is only available for completed backtests")

    settings = await BacktestSettingsRepository().get()
    if not ai_feedback_settings_ready(settings):
        raise ValueError(
            "Enable AI feedback and select a model in Settings → Backtesting"
        )

    existing = normalize_ai_feedback(
        run.get("ai_feedback") if isinstance(run.get("ai_feedback"), dict) else None
    )
    if existing and existing.get("status") == AI_FEEDBACK_STATUS_RUNNING:
        return run
    if run_id in _inflight_feedback:
        return run

    _inflight_feedback.add(run_id)

    # Optimistic running marker so the UI can poll immediately.
    model_id = str(settings["ai_feedback_model_id"])
    model_name = str(settings["ai_feedback_model_name"])
    effort = str(settings.get("ai_feedback_reasoning_effort") or "medium")
    updated = await mark_ai_feedback_running(
        run_id,
        model_id=model_id,
        model_name=model_name,
        reasoning_effort=effort,
    )

    async def _runner() -> None:
        try:
            await run_backtest_ai_feedback(run_id)
        except Exception:
            logger.exception("Background AI feedback task crashed for %s", run_id)
            _inflight_feedback.discard(run_id)
            try:
                await BacktestRunsRepository().update_ai_feedback(
                    run_id,
                    {
                        "status": AI_FEEDBACK_STATUS_FAILED,
                        "model_id": model_id,
                        "model_name": model_name,
                        "reasoning_effort": effort,
                        "markdown": None,
                        "suggestions": [],
                        "memory_notes": [],
                        "error": "AI feedback task failed to start",
                        "started_at": _now_iso(),
                        "finished_at": _now_iso(),
                        "usage": None,
                    },
                )
            except Exception:
                logger.exception("Failed to persist AI feedback crash for %s", run_id)

    try:
        asyncio.get_running_loop().create_task(
            _runner(), name=f"backtest-ai-feedback-{run_id}"
        )
    except RuntimeError:
        _inflight_feedback.discard(run_id)
        raise

    return updated or run


async def maybe_auto_analyze_backtest(run_id: str) -> None:
    """Coordinator hook: start feedback when auto-analyze settings allow it."""
    try:
        settings = await BacktestSettingsRepository().get()
        if not settings.get("ai_feedback_auto_on_complete"):
            return
        if not ai_feedback_settings_ready(settings):
            return
        run = await BacktestRunsRepository().get_by_id(run_id)
        if run is None or run.get("status") != BACKTEST_RUN_STATUS_COMPLETED:
            return
        existing = normalize_ai_feedback(
            run.get("ai_feedback") if isinstance(run.get("ai_feedback"), dict) else None
        )
        if existing and existing.get("status") in {
            AI_FEEDBACK_STATUS_RUNNING,
            AI_FEEDBACK_STATUS_COMPLETED,
        }:
            return
        await begin_ai_feedback_job(run_id)
    except Exception:
        logger.warning("Auto AI feedback skipped for run %s", run_id, exc_info=True)
