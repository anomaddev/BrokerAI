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

_FEEDBACK_SYSTEM_PROMPT = """\
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

Be specific and grounded in the supplied data. Do not invent trades or metrics.
"""

# Prevent overlapping auto/manual jobs for the same run on one API process.
_inflight_feedback: set[str] = set()


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


def build_backtest_feedback_messages(context: dict[str, Any]) -> list[dict[str, str]]:
    """Build chat messages for strategy-feedback analysis."""
    payload = json.dumps(context, default=str, separators=(",", ":"))
    if len(payload) > MAX_CONTEXT_JSON_CHARS:
        # Drop candle windows first, then signal samples, to stay in budget.
        slim = dict(context)
        slim["candle_windows"] = []
        slim["note"] = (
            "Candle windows omitted because context exceeded the size budget; "
            "rely on trades, stats, and period_summary."
        )
        payload = json.dumps(slim, default=str, separators=(",", ":"))
        if len(payload) > MAX_CONTEXT_JSON_CHARS:
            slim["signals_sample"] = slim.get("signals_sample", [])[:10]
            slim["filter_fails_sample"] = slim.get("filter_fails_sample", [])[:10]
            payload = json.dumps(slim, default=str, separators=(",", ":"))

    user = (
        "Analyze this completed BrokerAI backtest and suggest where the strategy "
        "could be improved. Data follows as JSON.\n\n"
        f"```json\n{payload}\n```"
    )
    return [
        {"role": "system", "content": _FEEDBACK_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


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
    candle_windows: list[dict[str, Any]] = []
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
            candle_windows = slice_candle_windows(
                candles,
                trades,
                timeframe=timeframe,
            )
        except Exception:
            logger.warning(
                "Failed to load candles for AI feedback on run %s", run_id, exc_info=True
            )

    equity = downsample_equity_for_feedback(list(run.get("equity_curve") or []))

    return {
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
        "params_snapshot": run.get("params_snapshot"),
        "stats": run.get("stats"),
        "equity_curve": equity,
        "trades": trades,
        "signals_sample": signals,
        "filter_fails_sample": filter_fails,
        "period_summary": period_summary,
        "candle_windows": candle_windows,
        "warn_logs": warn_logs,
    }


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
        context = await build_backtest_feedback_context(run_id)
        messages = build_backtest_feedback_messages(context)
        markdown = await analyze_with_model(
            model_type,
            base_url,
            resolved_name,
            messages,
            api_key if isinstance(api_key, str) else None,
            reasoning_effort=None if effort == "none" else str(effort),
            cost_context={
                "operation": "backtest_ai_feedback",
                "backtest_run_id": run_id,
            },
        )
        feedback = {
            "status": AI_FEEDBACK_STATUS_COMPLETED,
            "model_id": str(model_id),
            "model_name": resolved_name,
            "reasoning_effort": str(effort),
            "markdown": markdown,
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
