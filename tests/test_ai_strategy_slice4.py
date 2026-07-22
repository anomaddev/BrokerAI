"""Tests for AI Strategy Slice 4 — daily playbook backtests + memory feedback."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.ai_strategy.compile_playbook import compile_playbook_params, compile_playbook_strategy_doc
from brokerai.ai_strategy.daily_backtest import (
    ORIGIN_AI_STRATEGY_DAILY,
    daily_cadence_key,
    maybe_queue_daily_ai_strategy_backtests,
    skip_reason_for_strategy,
    strategy_allows_daily_ai_backtest,
)
from brokerai.ai_strategy.lifecycle import ensure_lifecycle_on_create
from brokerai.ai_strategy.memory_digest import (
    digest_content_unchanged,
    merge_feedback_notes_into_digest,
)
from brokerai.backtesting.ai_feedback import (
    apply_memory_feedback_to_digest,
    build_backtest_feedback_messages,
    is_ai_strategy_daily_run,
    parse_memory_notes_from_markdown,
    run_backtest_ai_feedback,
)
from brokerai.backtesting.feedback_suggestions import apply_suggestions_to_params
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUS_QUEUED,
    BACKTEST_RUN_STATUS_RUNNING,
    BacktestRunsRepository,
)
from brokerai.db.repositories.backtest_settings import (
    BacktestSettingsRepository,
    normalize_backtest_settings,
)
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.db.repositories.strategy_learning import StrategyMemoryDigestsRepository
from brokerai.strategies.params import prepare_params
from brokerai.strategies.registry import get_preset
from brokerai.trading.indicator_cache import IndicatorCache
from brokerai.trading.pipeline import ensure_trading_registries
from brokerai.trading.registries.signals import get_signal_evaluator
from tests.fixtures.mock_candles import generate_mock_candles

pytestmark = pytest.mark.usefixtures("sqlite_db")


def _ai_strategy(
    strategy_id: str = "ai-daily-1",
    *,
    enabled: bool = True,
    learn_enabled: bool = True,
    improve_enabled: bool = True,
) -> dict:
    preset = get_preset("ai_strategy")
    assert preset is not None
    params = prepare_params(
        preset,
        {
            "schema_version": 1,
            "timeframe": "M15",
            "ai": {"llm_mode": "off", "learn_enabled": learn_enabled},
        },
    )
    params["ai"]["learn_enabled"] = learn_enabled
    doc = ensure_lifecycle_on_create(
        {
            "id": strategy_id,
            "name": "AI Daily",
            "preset_id": "ai_strategy",
            "asset_class": "forex",
            "enabled": enabled,
            "instruments": ["EUR/USD"],
            "params": params,
            "ai_improve": {"enabled": improve_enabled, "last_queued_et_date": None},
        }
    )
    doc["enabled"] = enabled
    doc["instruments"] = ["EUR/USD"]
    doc["params"] = params
    doc["ai_improve"] = {"enabled": improve_enabled, "last_queued_et_date": None}
    return doc


async def _seed_strategy(doc: dict) -> dict:
    repo = StrategiesRepository()
    # Bypass create() validation path by writing via save_lifecycle after create-like insert.
    from brokerai.db.pg.client import session_scope
    from brokerai.db.pg.models import StrategyRow
    from brokerai.db.repositories.strategies import _sync_row_columns

    async with session_scope() as session:
        row = StrategyRow(
            id=doc["id"],
            asset_class=doc["asset_class"],
            name=doc["name"],
            enabled=bool(doc.get("enabled")),
            preset_id=doc.get("preset_id"),
            backtest_status=doc.get("backtest_status") or "idle",
            doc=doc,
        )
        _sync_row_columns(row, doc)
        session.add(row)
    fetched = await repo.get_by_id(doc["id"])
    assert fetched is not None
    return fetched


async def _seed_digest(strategy_id: str, *, version: int = 1) -> dict:
    return await StrategyMemoryDigestsRepository().create_version(
        strategy_id,
        {
            "standing_rules": ["Prefer London continuation after early impulse"],
            "anti_rules": ["Avoid chasing late NY spikes"],
            "summary": "Continuation bias",
        },
        version=version,
    )


def test_normalize_daily_backtest_settings_defaults():
    settings = normalize_backtest_settings({})
    assert settings["daily_ai_strategy_backtest_enabled"] is False
    assert settings["daily_ai_strategy_backtest_period"] == "6m"


def test_compiled_playbook_signal_no_llm_and_momentum():
    ensure_trading_registries()
    evaluator = get_signal_evaluator("compiled_playbook")
    assert evaluator is not None
    assert not hasattr(evaluator, "evaluate_async") or not callable(
        getattr(evaluator, "analyze_with_model", None)
    )

    candles = generate_mock_candles(200)
    # Force a short streak of higher closes at the end for long bias.
    for i in range(1, 5):
        base = float(candles[-5]["close"])
        candles[-5 + i]["close"] = base + i * 0.001
        candles[-5 + i]["open"] = base + (i - 1) * 0.001
        candles[-5 + i]["high"] = candles[-5 + i]["close"] + 0.0002
        candles[-5 + i]["low"] = candles[-5 + i]["open"] - 0.0002

    params = {
        "schema_version": 1,
        "timeframe": "M15",
        "min_candles": 20,
        "signal": {
            "type": "compiled_playbook",
            "bias": "long",
            "require_momentum": True,
            "momentum_bars": 3,
            "standing_rules": ["Prefer long continuation"],
            "anti_rules": [],
            "anti_active": False,
        },
        "risk": {"risk_per_trade_pct": 1.0, "max_trades_per_day": 3},
        "execution": {"sessions": ["London"], "min_confidence": 50},
    }
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [params])
    with patch("brokerai.bots.researcher.llm.analyze_with_model") as mock_llm:
        result = evaluator.evaluate(candles, params, cache)
        mock_llm.assert_not_called()
    assert result.metadata.get("llm_called") is False
    assert result.direction == "long"
    assert result.confidence > 0

    blocked = dict(params)
    blocked["signal"] = {**params["signal"], "anti_active": True}
    blocked_result = evaluator.evaluate(candles, blocked, cache)
    assert blocked_result.direction is None
    assert blocked_result.metadata.get("reason") == "anti_rule_active"


def test_compile_playbook_from_digest_strings():
    strategy = _ai_strategy()
    digest = {
        "version": 3,
        "standing_rules": ["Favor bullish continuation in London"],
        "anti_rules": ["Respect holiday liquidity when sizing"],
        "summary": "ok",
    }
    compiled = compile_playbook_params(strategy, digest)
    assert compiled is not None
    assert compiled["signal"]["type"] == "compiled_playbook"
    assert compiled["signal"]["bias"] == "long"
    assert compiled["signal"]["digest_version"] == "3"
    assert compiled["signal"]["anti_active"] is False
    # No cautionary tokens → default gate.
    assert compiled["signal"]["momentum_bars"] == 3
    assert compiled["execution"]["min_confidence"] == 55
    assert compiled["risk"] == strategy["params"]["risk"]
    assert compiled["ai"]["llm_mode"] == "off"
    assert compile_playbook_params(strategy, None) is None
    assert compile_playbook_params(strategy, {"standing_rules": [], "anti_rules": []}) is None


def test_compile_playbook_honors_explicit_bias_and_caution_gate():
    """Feedback bias + cautionary antis must change the compiled gate (anti-clone)."""
    strategy = _ai_strategy()
    long_seed = {
        "version": 1,
        "standing_rules": [
            "Bias buy-the-dip while funding favors high-yielders",
            "Prefer bullish continuation in London",
            "Lean long on risk-on carry",
        ],
        "anti_rules": ["Avoid chasing late NY spikes"],
        "summary": "seed long",
        "bias": None,
    }
    seed_compiled = compile_playbook_params(strategy, long_seed)
    assert seed_compiled is not None
    assert seed_compiled["signal"]["bias"] == "long"
    assert seed_compiled["signal"]["momentum_bars"] == 3

    flipped = {
        "version": 2,
        # Newest-first: short lesson outweighs older long seed block.
        "standing_rules": [
            "Fade overextended rallies; prefer short mean-reversion",
            "Bias buy-the-dip while funding favors high-yielders",
            "Prefer bullish continuation in London",
            "Lean long on risk-on carry",
        ],
        "anti_rules": [
            "Stand aside through MOF intervention alerts",
            "Avoid momentum-only chases at extremes",
            "Do not force late-NY fades",
            "Avoid thin liquidity opens",
        ],
        "summary": "Fade overextended rallies · Stand aside through MOF…",
        "bias": "short",
    }
    next_compiled = compile_playbook_params(strategy, flipped)
    assert next_compiled is not None
    assert next_compiled["signal"]["bias"] == "short"
    assert next_compiled["signal"]["digest_bias"] == "short"
    # Four cautionary antis → +1 momentum bar and higher confidence / cooldown.
    assert next_compiled["signal"]["momentum_bars"] == 4
    assert next_compiled["signal"]["min_confidence"] > seed_compiled["signal"]["min_confidence"]
    assert next_compiled["execution"]["min_confidence"] > seed_compiled["execution"]["min_confidence"]
    assert next_compiled["execution"]["post_stop_cooldown_bars"] >= 4
    assert next_compiled["risk"]["max_trades_per_day"] <= seed_compiled["risk"]["max_trades_per_day"]


def test_compile_playbook_conditional_stand_aside_does_not_kill_switch():
    """Regime 'stand aside when…' antis must not zero the whole book."""
    strategy = _ai_strategy()
    digest = {
        "version": 4,
        "standing_rules": ["Lean long buy-the-dip USD/JPY on London holds"],
        "anti_rules": [
            "Stand aside through explicit MOF/BoJ alert windows",
            "Stand aside momentum-only chases at multi-decade extremes",
            "Avoid large naked USD/JPY direction while geopolitics remain two-way",
        ],
        "summary": "selective long",
    }
    compiled = compile_playbook_params(strategy, digest)
    assert compiled is not None
    assert compiled["signal"]["anti_active"] is False
    assert compiled["signal"]["bias"] == "long"
    # Soft caution still tightens the gate without a hard kill.
    assert compiled["signal"]["momentum_bars"] >= 4

    killed = compile_playbook_params(
        strategy,
        {
            "version": 5,
            "standing_rules": ["Lean long buy-the-dip"],
            "anti_rules": ["Kill switch — halt trading until digest refresh"],
            "summary": "halted",
        },
    )
    assert killed is not None
    assert killed["signal"]["anti_active"] is True


def test_merge_feedback_newest_first_and_fingerprint_noop():
    prior = {
        "standing_rules": ["old long seed", "another long seed"],
        "anti_rules": ["old anti"],
        "summary": "old long seed summary that fills the preview forever",
        "bias": "long",
    }
    notes = [
        {
            "id": "n1",
            "kind": "standing_rule",
            "text": "Prefer short mean-reversion at extremes",
            "bias": "short",
        },
        {
            "id": "n2",
            "kind": "anti_rule",
            "text": "Stand aside through MOF alerts",
            "bias": None,
        },
    ]
    merged = merge_feedback_notes_into_digest(prior, notes, strategy_id="s1")
    assert merged["standing_rules"][0] == "Prefer short mean-reversion at extremes"
    assert merged["anti_rules"][0] == "Stand aside through MOF alerts"
    assert merged["summary"].startswith("Prefer short mean-reversion")
    assert merged["bias"] == "short"
    assert not digest_content_unchanged(prior, merged)

    # Same notes again → identical learning fingerprint (no version bump).
    again = merge_feedback_notes_into_digest(merged, notes, strategy_id="s1")
    assert digest_content_unchanged(merged, again)


@pytest.mark.asyncio
async def test_feedback_apply_then_next_compile_binds_updated_memory():
    """Startup/trade loop contract: feedback → new digest → next compile uses it."""
    strategy = await _seed_strategy(_ai_strategy("ai-bind-1", enabled=True, learn_enabled=True))
    await StrategyMemoryDigestsRepository().create_version(
        strategy["id"],
        {
            "standing_rules": ["Bias buy-the-dip long continuation"],
            "anti_rules": [],
            "summary": "seed long",
            "bias": "long",
        },
        version=1,
    )
    first = compile_playbook_strategy_doc(
        strategy,
        await StrategyMemoryDigestsRepository().get_latest(strategy["id"]),
    )
    assert first is not None
    assert first["params"]["signal"]["bias"] == "long"
    assert first["params"]["signal"]["digest_version"] == "1"

    applied = await apply_memory_feedback_to_digest(
        strategy["id"],
        [
            {
                "id": "flip",
                "kind": "standing_rule",
                "text": "Fade rallies; prefer short at extremes",
                "bias": "short",
            },
            {
                "id": "caution",
                "kind": "anti_rule",
                "text": "Avoid late-NY chase entries",
            },
        ],
        source="ai_strategy_startup_trade",
    )
    assert applied is not None
    assert applied["version"] == 2
    assert applied["standing_rules"][0] == "Fade rallies; prefer short at extremes"
    assert applied["bias"] == "short"

    second = compile_playbook_strategy_doc(
        strategy,
        await StrategyMemoryDigestsRepository().get_latest(strategy["id"]),
    )
    assert second is not None
    assert second["params"]["signal"]["digest_version"] == "2"
    assert second["params"]["signal"]["bias"] == "short"
    assert second["params"]["signal"]["momentum_bars"] >= first["params"]["signal"]["momentum_bars"]
    assert second["params"]["signal"]["standing_rules"][0] == (
        "Fade rallies; prefer short at extremes"
    )


def test_cadence_skip_reasons():
    strategy = _ai_strategy(learn_enabled=True)
    digest = {
        "version": 1,
        "standing_rules": ["long bias"],
        "anti_rules": [],
    }
    assert (
        skip_reason_for_strategy(
            strategy,
            digest=digest,
            existing_cadence=None,
            prior_daily_runs=[],
            et_date="2026-07-22",
        )
        is None
    )
    assert (
        skip_reason_for_strategy(
            strategy,
            digest=None,
            existing_cadence=None,
            prior_daily_runs=[],
            et_date="2026-07-22",
        )
        == "no_digest"
    )
    assert (
        skip_reason_for_strategy(
            strategy,
            digest=digest,
            existing_cadence={"id": "r1"},
            prior_daily_runs=[],
            et_date="2026-07-22",
        )
        == "already_queued_today"
    )
    assert (
        skip_reason_for_strategy(
            strategy,
            digest=digest,
            existing_cadence=None,
            prior_daily_runs=[{"status": BACKTEST_RUN_STATUS_RUNNING, "digest_version": "9"}],
            et_date="2026-07-22",
        )
        == "prior_still_running"
    )
    assert (
        skip_reason_for_strategy(
            strategy,
            digest=digest,
            existing_cadence=None,
            prior_daily_runs=[
                {"status": "completed", "digest_version": "1"},
            ],
            et_date="2026-07-22",
        )
        == "digest_unchanged"
    )
    disabled = _ai_strategy(learn_enabled=False)
    assert not strategy_allows_daily_ai_backtest(disabled)


@pytest.mark.asyncio
async def test_daily_queue_and_skip_idempotent():
    strategy = await _seed_strategy(_ai_strategy("ai-q1", enabled=True, learn_enabled=True))
    await _seed_digest(strategy["id"], version=1)
    await BacktestSettingsRepository().update(
        daily_ai_strategy_backtest_enabled=True,
        daily_ai_strategy_backtest_period="3m",
    )
    now = datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc)
    first = await maybe_queue_daily_ai_strategy_backtests(now=now)
    assert len(first["queued"]) == 1
    run = first["queued"][0]
    assert run["origin"] == ORIGIN_AI_STRATEGY_DAILY
    assert run["cadence_key"] == daily_cadence_key(strategy["id"], et_date="2026-07-22")
    assert run["digest_version"] == "1"
    assert run["period"] == "3m"
    assert run["params_snapshot"]["signal"]["type"] == "compiled_playbook"

    second = await maybe_queue_daily_ai_strategy_backtests(now=now)
    assert second["queued"] == []
    assert second["skipped"].get(strategy["id"]) == "already_queued_today"


@pytest.mark.asyncio
async def test_feedback_fork_memory_not_ema_allowlist():
    assert is_ai_strategy_daily_run({"origin": ORIGIN_AI_STRATEGY_DAILY})
    assert not is_ai_strategy_daily_run({"origin": None})

    messages = build_backtest_feedback_messages({"run": {"id": "x"}}, memory_oriented=True)
    system = messages[0]["content"].lower()
    user = messages[1]["content"].lower()
    assert "memory digest" in system
    assert "instrument trend" in system
    assert "should have traded" in system
    assert "trade count" in system  # explicitly told NOT to judge by it
    assert "filters.atr" not in system
    assert "signal" in user and "p&l" in user

    markdown = (
        "## Summary\nPlaybook learned.\n\n"
        "```json\n"
        '{"memory_notes":[{"id":"n1","kind":"standing_rule","text":"Hold London winners","bias":"long"}]}\n'
        "```"
    )
    cleaned, notes = parse_memory_notes_from_markdown(markdown)
    assert "Hold London winners" in notes[0]["text"]
    assert "```" not in cleaned

    sid = "ai-mem-1"
    await StrategyMemoryDigestsRepository().create_version(
        sid,
        {"standing_rules": ["old"], "anti_rules": [], "summary": "prior"},
        version=1,
    )
    applied = await apply_memory_feedback_to_digest(sid, notes)
    assert applied is not None
    assert applied["version"] == 2
    assert applied["standing_rules"][0] == "Hold London winners"
    assert "Hold London winners" in applied["standing_rules"]
    assert applied["summary"].startswith("Hold London winners")
    assert applied.get("bias") == "long"

    # Duplicate notes must not bump version when content is unchanged.
    again = await apply_memory_feedback_to_digest(sid, notes)
    assert again is not None
    assert again["version"] == 2
    assert again["id"] == applied["id"]

    # Guard: EMA apply helper is unused for memory notes path.
    params = {"filters": [{"id": "atr", "type": "atr", "min_value": 0.0008}]}
    untouched = apply_suggestions_to_params(
        params,
        [{"id": "x", "path": "filters.atr.min_value", "to": 0.05}],
    )
    # apply_suggestions still works for EMA runs; memory fork simply never calls it.
    assert untouched["filters"][0]["min_value"] == 0.05


@pytest.mark.asyncio
async def test_run_backtest_ai_feedback_memory_fork_persists_notes():
    strategy = await _seed_strategy(_ai_strategy("ai-fb-1", enabled=True, learn_enabled=True))
    await _seed_digest(strategy["id"], version=1)
    compiled = compile_playbook_params(
        strategy,
        await StrategyMemoryDigestsRepository().get_latest(strategy["id"]),
    )
    assert compiled is not None
    created = await BacktestRunsRepository().create_queued_runs(
        [{**strategy, "params": compiled}],
        origin=ORIGIN_AI_STRATEGY_DAILY,
        cadence_key="ai-fb-1:2026-07-22",
        digest_version="1",
    )
    run_id = created[0]["id"]
    await BacktestRunsRepository().finish_run(run_id, status="completed", stats={"total_trades": 2})

    await BacktestSettingsRepository().update(
        ai_feedback_enabled=True,
        ai_feedback_model_id="model-1",
        ai_feedback_model_name="gpt-test",
    )

    model = {
        "id": "model-1",
        "enabled": True,
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-test",
        "api_key": "sk-test",
        "title": "Test",
    }
    memory_json = (
        "## Summary\nok\n\n```json\n"
        '{"memory_notes":[{"id":"a1","kind":"anti_rule","text":"No late-NY fade"}]}\n'
        "```"
    )
    from brokerai.backtesting import ai_feedback as af

    with (
        patch(
            "brokerai.backtesting.ai_feedback.AiModelsRepository.find_enabled_by_id",
            new_callable=AsyncMock,
            return_value=model,
        ),
        patch(
            "brokerai.backtesting.ai_feedback.bind_source_model",
            return_value=model,
        ),
        patch(
            "brokerai.backtesting.ai_feedback.analyze_with_model",
            new_callable=AsyncMock,
            return_value=memory_json,
        ) as mock_llm,
        patch.object(af, "parse_suggestions_from_markdown") as mock_parse_ema,
        patch.object(af, "apply_suggestions_to_params", create=True) as mock_apply,
    ):
        updated = await run_backtest_ai_feedback(run_id)
        mock_parse_ema.assert_not_called()
        mock_apply.assert_not_called()
        assert mock_llm.await_args.kwargs["cost_context"]["operation"] == (
            "ai_strategy_daily_feedback"
        )

    feedback = updated.get("ai_feedback") or {}
    assert feedback.get("status") == "completed"
    assert feedback.get("suggestions") == []
    assert any(n.get("text") == "No late-NY fade" for n in (feedback.get("memory_notes") or []))
    digest = await StrategyMemoryDigestsRepository().get_latest(strategy["id"])
    assert digest is not None
    assert digest["version"] == 2
    assert "No late-NY fade" in digest["anti_rules"]
