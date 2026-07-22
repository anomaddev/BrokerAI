"""Batched outcome learning for AI Strategy (Slice 3).

Never calls the LLM on each trade close. Instead:
1. ``queue_learning_job`` enqueues when enough *new* outcomes accumulate
   (default ≥5) or when ``force=True``.
2. ``run_learning_job`` builds a compact stratified win/loss package, calls
   ``analyze_with_model`` once with ``operation=strategy_learn`` (spend-gated),
   and versions a ``strategy_memory_digests`` row.

Respects ``params.ai.learn_enabled`` unless ``force=True``.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from brokerai.bots.researcher.llm import analyze_with_model
from brokerai.cost.llm_guard import LlmBudgetExceeded
from brokerai.db.repositories.ai_models import AiModelsRepository, bind_source_model
from brokerai.db.repositories.shadow_trading import TradeOutcomeRecordsRepository
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.db.repositories.strategy_learning import (
    LEARNING_JOB_STATUS_COMPLETED,
    LEARNING_JOB_STATUS_FAILED,
    LEARNING_JOB_STATUS_QUEUED,
    LearningJobsRepository,
    StrategyMemoryDigestsRepository,
)

logger = logging.getLogger(__name__)

# Threshold of new outcomes (since last digest coverage) before auto-queue.
MIN_NEW_OUTCOMES_FOR_LEARN = 5

# Compact evidence package caps (wins AND losses stratified).
MAX_EVIDENCE_WINS = 8
MAX_EVIDENCE_LOSSES = 8

# Digest / prompt caps — keep hot-path context small.
MAX_STANDING_RULES = 12
MAX_ANTI_RULES = 12
MAX_RULE_CHARS = 160
MAX_DIGEST_PROMPT_CHARS = 1200
MAX_SUMMARY_CHARS = 400


def _ai_section(params: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    raw = params.get("ai")
    return dict(raw) if isinstance(raw, dict) else {}


def _parse_iso_dt(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _rule_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("text") or "").strip()
    return ""


def _normalize_rules(raw: Any, *, limit: int, kind: str) -> list[dict[str, Any]]:
    """Normalize LLM/rule lists into structured ``{text, kind}`` dicts.

    Accepts plain strings (LLM JSON) or dicts with a ``text`` field (Slice 4).
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        text = _truncate(_rule_text(item), MAX_RULE_CHARS)
        if not text:
            continue
        rule: dict[str, Any] = {"text": text, "kind": kind}
        if isinstance(item, dict):
            for key in ("id", "bias", "keywords", "priority"):
                if key in item and item[key] is not None:
                    rule[key] = item[key]
        out.append(rule)
        if len(out) >= limit:
            break
    return out


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("empty model response")
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", stripped)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("learning JSON must be an object")
    return data


def _compact_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": outcome.get("id"),
        "pair": outcome.get("pair"),
        "timeframe": outcome.get("timeframe") or "",
        "direction": outcome.get("direction"),
        "mode": outcome.get("mode"),
        "realized_pnl": float(outcome.get("realized_pnl") or 0.0),
        "close_reason": outcome.get("close_reason") or outcome.get("exit_reason"),
        "entry_ts": outcome.get("entry_ts"),
        "exit_ts": outcome.get("exit_ts"),
        "hypothesis": _truncate(str(outcome.get("hypothesis") or ""), 120) or None,
    }


def build_stratified_evidence(
    outcomes: list[dict[str, Any]],
    *,
    max_wins: int = MAX_EVIDENCE_WINS,
    max_losses: int = MAX_EVIDENCE_LOSSES,
) -> dict[str, Any]:
    """Split outcomes into wins/losses and take newest of each (stratified).

    Flat / zero-PnL trades are omitted from evidence lists but counted in totals.
    Outcomes are assumed newest-first.
    """
    wins: list[dict[str, Any]] = []
    losses: list[dict[str, Any]] = []
    flats = 0
    for outcome in outcomes:
        pnl = float(outcome.get("realized_pnl") or 0.0)
        if pnl > 0:
            if len(wins) < max_wins:
                wins.append(_compact_outcome(outcome))
        elif pnl < 0:
            if len(losses) < max_losses:
                losses.append(_compact_outcome(outcome))
        else:
            flats += 1
    return {
        "wins": wins,
        "losses": losses,
        "total_outcomes": len(outcomes),
        "win_count": sum(1 for o in outcomes if float(o.get("realized_pnl") or 0) > 0),
        "loss_count": sum(1 for o in outcomes if float(o.get("realized_pnl") or 0) < 0),
        "flat_count": flats,
    }


def format_digest_for_prompt(digest: dict[str, Any] | None) -> str:
    """Format a digest for ModelSignalRuntime — small and capped."""
    if not digest:
        return "Memory digest: (none yet)"
    standing = _normalize_rules(
        digest.get("standing_rules"), limit=MAX_STANDING_RULES, kind="standing_rule"
    )
    anti = _normalize_rules(
        digest.get("anti_rules"), limit=MAX_ANTI_RULES, kind="anti_rule"
    )
    summary = _truncate(str(digest.get("summary") or ""), MAX_SUMMARY_CHARS)
    version = digest.get("version")
    lines = [
        f"Memory digest v{version} (standing/anti rules from past outcomes — soft bias only):",
    ]
    if summary:
        lines.append(f"Summary: {summary}")
    if standing:
        lines.append("Standing rules:")
        lines.extend(f"- {rule['text']}" for rule in standing)
    if anti:
        lines.append("Anti-rules (avoid):")
        lines.extend(f"- {rule['text']}" for rule in anti)
    if not standing and not anti and not summary:
        lines.append("(empty rules)")
    text = "\n".join(lines)
    return _truncate(text, MAX_DIGEST_PROMPT_CHARS)


def _build_learn_messages(
    *,
    strategy_id: str,
    evidence: dict[str, Any],
    prior_digest: dict[str, Any] | None,
) -> list[dict[str, str]]:
    prior_block = format_digest_for_prompt(prior_digest)
    system = (
        "You are BrokerAI's AI Strategy learning engine. "
        "Given stratified win and loss trade outcomes, update a compact memory digest. "
        "Return ONLY a single JSON object (no markdown) with keys: "
        "standing_rules (string[]), anti_rules (string[]), summary (string). "
        "Standing rules: durable patterns that helped wins. "
        "Anti-rules: patterns to avoid from losses. "
        "Keep each rule short and actionable. Cap at 12 rules per list. "
        "Do not invent trades. Prefer revising prior digest over rewriting from scratch."
    )
    user = (
        f"Strategy id: {strategy_id}\n"
        f"Evidence totals: total={evidence['total_outcomes']} "
        f"wins={evidence['win_count']} losses={evidence['loss_count']} "
        f"flats={evidence['flat_count']}\n\n"
        f"Prior digest:\n{prior_block}\n\n"
        f"Win sample (newest first):\n{json.dumps(evidence['wins'], default=str)}\n\n"
        f"Loss sample (newest first):\n{json.dumps(evidence['losses'], default=str)}\n\n"
        "Respond with the Learning JSON only."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_learning_response(raw_text: str) -> dict[str, Any]:
    data = _extract_json_object(raw_text)
    return {
        "standing_rules": _normalize_rules(
            data.get("standing_rules"), limit=MAX_STANDING_RULES, kind="standing_rule"
        ),
        "anti_rules": _normalize_rules(
            data.get("anti_rules"), limit=MAX_ANTI_RULES, kind="anti_rule"
        ),
        "summary": _truncate(str(data.get("summary") or ""), MAX_SUMMARY_CHARS),
    }


async def queue_learning_job(
    strategy_id: str,
    *,
    force: bool = False,
    strategy: dict[str, Any] | None = None,
    min_new_outcomes: int = MIN_NEW_OUTCOMES_FOR_LEARN,
    outcomes_repo: TradeOutcomeRecordsRepository | None = None,
    digests_repo: StrategyMemoryDigestsRepository | None = None,
    jobs_repo: LearningJobsRepository | None = None,
    strategies_repo: StrategiesRepository | None = None,
) -> dict[str, Any] | None:
    """Enqueue a learning job when the new-outcome threshold is met (or force).

    Returns the queued job dict, or None when skipped (learn disabled, below
    threshold, or an open job already exists).

    Edge cases:
    - ``force=True`` bypasses ``learn_enabled`` and the outcome threshold, but
      still skips when an open (queued/running) job exists for the strategy.
    - Idempotent for concurrent closes: at most one open job per strategy.
    """
    sid = (strategy_id or "").strip()
    if not sid:
        return None

    outcomes_repo = outcomes_repo or TradeOutcomeRecordsRepository()
    digests_repo = digests_repo or StrategyMemoryDigestsRepository()
    jobs_repo = jobs_repo or LearningJobsRepository()
    strategies_repo = strategies_repo or StrategiesRepository()

    doc = strategy
    if doc is None:
        try:
            doc = await strategies_repo.get_by_id(sid)
        except Exception:
            logger.exception("queue_learning_job: strategy lookup failed for %s", sid)
            doc = None

    ai = _ai_section((doc or {}).get("params") if isinstance(doc, dict) else None)
    learn_enabled = bool(ai.get("learn_enabled"))
    if not force and not learn_enabled:
        return None

    if await jobs_repo.has_open_job(sid):
        logger.debug("Learning job already open for strategy=%s — skip queue", sid)
        return None

    since = await digests_repo.covered_through(sid)
    new_count = await outcomes_repo.count_since(sid, since=since)
    if not force and new_count < max(1, int(min_new_outcomes)):
        return None

    job = await jobs_repo.enqueue(
        sid,
        {
            "force": bool(force),
            "new_outcome_count": new_count,
            "since": since.isoformat() if since else None,
            "learn_enabled": learn_enabled,
            "status": LEARNING_JOB_STATUS_QUEUED,
        },
    )
    logger.info(
        "Queued learning job %s strategy=%s new_outcomes=%s force=%s",
        job["id"],
        sid,
        new_count,
        force,
    )
    return job


async def run_learning_job(
    job_id: str,
    *,
    outcomes_repo: TradeOutcomeRecordsRepository | None = None,
    digests_repo: StrategyMemoryDigestsRepository | None = None,
    jobs_repo: LearningJobsRepository | None = None,
    strategies_repo: StrategiesRepository | None = None,
    models_repo: AiModelsRepository | None = None,
) -> dict[str, Any]:
    """Execute one queued learning job: one spend-gated LLM call → new digest version.

    Failures mark the job ``failed`` and re-raise (except budget/parse which are
    recorded then returned as failed job dicts without raising when already settled).
    """
    outcomes_repo = outcomes_repo or TradeOutcomeRecordsRepository()
    digests_repo = digests_repo or StrategyMemoryDigestsRepository()
    jobs_repo = jobs_repo or LearningJobsRepository()
    strategies_repo = strategies_repo or StrategiesRepository()
    models_repo = models_repo or AiModelsRepository()

    job = await jobs_repo.get_by_id(job_id)
    if job is None:
        raise ValueError(f"learning job not found: {job_id}")
    if job.get("status") == LEARNING_JOB_STATUS_COMPLETED:
        return job
    if job.get("status") == LEARNING_JOB_STATUS_FAILED:
        return job

    running = await jobs_repo.mark_running(job_id)
    if running is None:
        raise ValueError(f"learning job not found: {job_id}")

    strategy_id = str(running["strategy_id"])
    try:
        strategy = await strategies_repo.get_by_id(strategy_id)
        if strategy is None:
            raise ValueError(f"strategy not found: {strategy_id}")
        ai = _ai_section(strategy.get("params"))
        model_id = ai.get("model_id")
        if not model_id:
            raise ValueError("params.ai.model_id missing for learning")

        source = await models_repo.find_enabled_by_id(str(model_id))
        if source is None:
            raise ValueError(f"model missing or disabled: {model_id}")
        chosen_name = ai.get("model_name")
        bound = bind_source_model(
            source, str(chosen_name).strip() if chosen_name else None
        )
        model_type = str(bound.get("type") or "")
        base_url = str(bound.get("base_url") or "")
        model_name = str(bound.get("model_name") or "")
        api_key = bound.get("api_key") or None
        if not model_type or not base_url or not model_name:
            raise ValueError("model incomplete for learning")

        prior = await digests_repo.get_latest(strategy_id)
        since = _parse_iso_dt((running.get("since") if running.get("since") else None))
        if since is None:
            since = await digests_repo.covered_through(strategy_id)

        outcomes = await outcomes_repo.list_since(strategy_id, since=since, limit=500)
        if not outcomes and not running.get("force"):
            raise ValueError("no new outcomes to learn from")

        evidence = build_stratified_evidence(outcomes)
        messages = _build_learn_messages(
            strategy_id=strategy_id,
            evidence=evidence,
            prior_digest=prior,
        )
        covered = None
        if outcomes:
            covered = max(
                (_parse_iso_dt(o.get("exit_ts")) for o in outcomes),
                default=None,
            )

        asof_id = (
            covered.isoformat()
            if covered is not None
            else f"job:{job_id}:v{(prior or {}).get('version', 0)}"
        )
        try:
            raw = await analyze_with_model(
                model_type,
                base_url,
                model_name,
                messages,
                api_key if isinstance(api_key, str) else None,
                cost_context={
                    "operation": "strategy_learn",
                    "source": "ai_strategy",
                    "strategy_id": strategy_id,
                    "asof_id": asof_id,
                    "billable": True,
                    "model_id": str(model_id),
                    "learning_job_id": job_id,
                },
            )
        except LlmBudgetExceeded as exc:
            failed = await jobs_repo.mark_failed(
                job_id, error=f"budget_exceeded:{exc.reason}"
            )
            return failed or {"id": job_id, "status": LEARNING_JOB_STATUS_FAILED}

        parsed = parse_learning_response(raw)
        next_version = await digests_repo.next_version(strategy_id)
        digest_doc = {
            "standing_rules": parsed["standing_rules"],
            "anti_rules": parsed["anti_rules"],
            "summary": parsed["summary"],
            "learning_job_id": job_id,
            "outcome_ids": [o.get("id") for o in outcomes if o.get("id")],
            "outcome_count": len(outcomes),
            "win_count": evidence["win_count"],
            "loss_count": evidence["loss_count"],
            "covered_through": covered.isoformat() if covered else None,
            "prior_version": (prior or {}).get("version"),
            "model_id": str(model_id),
        }
        digest = await digests_repo.create_version(
            strategy_id, digest_doc, version=next_version
        )
        completed = await jobs_repo.mark_completed(
            job_id,
            digest_id=digest["id"],
            digest_version=digest["version"],
            extra={
                "outcome_count": len(outcomes),
                "win_count": evidence["win_count"],
                "loss_count": evidence["loss_count"],
            },
        )
        logger.info(
            "Learning job %s completed strategy=%s digest_v=%s outcomes=%s",
            job_id,
            strategy_id,
            digest["version"],
            len(outcomes),
        )
        return completed or digest
    except Exception as exc:
        logger.exception("Learning job %s failed for strategy=%s", job_id, strategy_id)
        await jobs_repo.mark_failed(job_id, error=str(exc))
        raise


async def drain_queued_learning_jobs(
    *,
    limit: int = 1,
    jobs_repo: LearningJobsRepository | None = None,
) -> dict[str, Any]:
    """Run up to ``limit`` queued learning jobs (Secretary slow drain).

    Failures on individual jobs are logged; remaining jobs stay queued/failed
    independently so one bad strategy cannot block the queue forever.
    """
    jobs_repo = jobs_repo or LearningJobsRepository()
    queued = await jobs_repo.list_queued(limit=max(1, min(int(limit), 10)))
    completed = 0
    failed = 0
    for job in queued:
        job_id = str(job.get("id") or "")
        if not job_id:
            continue
        try:
            await run_learning_job(job_id, jobs_repo=jobs_repo)
            completed += 1
        except Exception:
            failed += 1
            logger.exception("drain_queued_learning_jobs: job %s failed", job_id)
    return {"considered": len(queued), "completed": completed, "failed": failed}
