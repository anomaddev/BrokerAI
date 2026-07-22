"""Tests for AI Strategy Slice 3 — batched outcome learning + digests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.ai_strategy.learning import (
    MIN_NEW_OUTCOMES_FOR_LEARN,
    build_stratified_evidence,
    format_digest_for_prompt,
    parse_learning_response,
    queue_learning_job,
    run_learning_job,
)
from brokerai.ai_strategy.shadow_dispatch import close_shadow_lot_with_outcome
from brokerai.bots.researcher.trade_context import load_weekly_bot_results
from brokerai.db.repositories.shadow_trading import TradeOutcomeRecordsRepository
from brokerai.db.repositories.strategy_learning import (
    LEARNING_JOB_STATUS_COMPLETED,
    LEARNING_JOB_STATUS_QUEUED,
    LearningJobsRepository,
    StrategyMemoryDigestsRepository,
)
from brokerai.trading.indicator_cache import IndicatorCache
from brokerai.trading.presets.ai_strategy.runtime import (
    ModelSignalRuntime,
    clear_decision_cache,
)
from brokerai.strategies.params import prepare_params
from brokerai.strategies.registry import get_preset
from tests.fixtures.mock_candles import generate_mock_candles

pytestmark = pytest.mark.usefixtures("sqlite_db")


@pytest.fixture(autouse=True)
def _clear_ai_decision_cache():
    clear_decision_cache()
    yield
    clear_decision_cache()


def _strategy_doc(
    strategy_id: str = "strat-learn",
    *,
    learn_enabled: bool = True,
    model_id: str = "model-1",
) -> dict:
    preset = get_preset("ai_strategy")
    assert preset is not None
    params = prepare_params(
        preset,
        {
            "schema_version": 1,
            "timeframe": "M15",
            "ai": {
                "llm_mode": "interval",
                "model_id": model_id,
                "learn_enabled": learn_enabled,
                "min_llm_interval_minutes": 15,
            },
        },
    )
    params["ai"]["model_id"] = model_id
    params["ai"]["learn_enabled"] = learn_enabled
    return {
        "id": strategy_id,
        "name": "AI Learn",
        "preset_id": "ai_strategy",
        "params": params,
    }


def _enabled_model(*, model_id: str = "model-1") -> dict:
    return {
        "id": model_id,
        "enabled": True,
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-test",
        "api_key": "sk-test",
        "title": "Test Model",
    }


async def _seed_outcomes(
    strategy_id: str,
    *,
    n_wins: int,
    n_losses: int,
    base: datetime | None = None,
) -> list[dict]:
    repo = TradeOutcomeRecordsRepository()
    stamp = base or datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    saved: list[dict] = []
    idx = 0
    for _ in range(n_wins):
        idx += 1
        exit_ts = stamp + timedelta(minutes=idx)
        saved.append(
            await repo.append(
                {
                    "strategy_id": strategy_id,
                    "mode": "shadow",
                    "pair": "EUR/USD",
                    "timeframe": "M15",
                    "direction": "long",
                    "entry_ts": (exit_ts - timedelta(hours=1)).isoformat(),
                    "exit_ts": exit_ts.isoformat(),
                    "realized_pnl": 12.5,
                    "close_reason": "take_profit",
                }
            )
        )
    for _ in range(n_losses):
        idx += 1
        exit_ts = stamp + timedelta(minutes=idx)
        saved.append(
            await repo.append(
                {
                    "strategy_id": strategy_id,
                    "mode": "shadow",
                    "pair": "GBP/USD",
                    "timeframe": "M15",
                    "direction": "short",
                    "entry_ts": (exit_ts - timedelta(hours=1)).isoformat(),
                    "exit_ts": exit_ts.isoformat(),
                    "realized_pnl": -8.0,
                    "close_reason": "stop_loss",
                }
            )
        )
    return saved


def test_stratified_evidence_includes_wins_and_losses():
    outcomes = [
        {"id": "w1", "realized_pnl": 5, "pair": "EUR/USD", "direction": "long"},
        {"id": "l1", "realized_pnl": -3, "pair": "GBP/USD", "direction": "short"},
        {"id": "w2", "realized_pnl": 2, "pair": "USD/JPY", "direction": "long"},
        {"id": "f1", "realized_pnl": 0, "pair": "AUD/USD", "direction": "long"},
    ]
    evidence = build_stratified_evidence(outcomes, max_wins=2, max_losses=2)
    assert len(evidence["wins"]) == 2
    assert len(evidence["losses"]) == 1
    assert evidence["win_count"] == 2
    assert evidence["loss_count"] == 1
    assert evidence["flat_count"] == 1


def test_parse_learning_response_and_digest_format():
    parsed = parse_learning_response(
        '{"standing_rules":["Prefer London continuation"],'
        '"anti_rules":["Avoid chasing NY open spikes"],'
        '"summary":"Favor continuation; fade chase entries."}'
    )
    assert parsed["standing_rules"][0]["text"] == "Prefer London continuation"
    assert parsed["anti_rules"][0]["text"] == "Avoid chasing NY open spikes"
    text = format_digest_for_prompt({"version": 2, **parsed})
    assert "Memory digest v2" in text
    assert "Prefer London continuation" in text
    assert "Avoid chasing NY open spikes" in text


@pytest.mark.asyncio
async def test_queue_respects_learn_enabled_and_threshold():
    sid = "s-threshold"
    strategies = AsyncMock()
    strategies.get_by_id = AsyncMock(
        return_value=_strategy_doc(sid, learn_enabled=False)
    )
    await _seed_outcomes(sid, n_wins=3, n_losses=3)

    skipped = await queue_learning_job(
        sid,
        strategies_repo=strategies,
        min_new_outcomes=MIN_NEW_OUTCOMES_FOR_LEARN,
    )
    assert skipped is None

    strategies.get_by_id = AsyncMock(
        return_value=_strategy_doc(sid, learn_enabled=True)
    )
    # 6 outcomes >= 5
    job = await queue_learning_job(
        sid,
        strategies_repo=strategies,
        min_new_outcomes=MIN_NEW_OUTCOMES_FOR_LEARN,
    )
    assert job is not None
    assert job["status"] == LEARNING_JOB_STATUS_QUEUED
    assert job["new_outcome_count"] >= MIN_NEW_OUTCOMES_FOR_LEARN

    # Second queue while open → skip
    again = await queue_learning_job(sid, strategies_repo=strategies, force=True)
    assert again is None


@pytest.mark.asyncio
async def test_force_queues_below_threshold():
    sid = "s-force"
    strategies = AsyncMock()
    strategies.get_by_id = AsyncMock(
        return_value=_strategy_doc(sid, learn_enabled=False)
    )
    await _seed_outcomes(sid, n_wins=1, n_losses=0)
    job = await queue_learning_job(sid, force=True, strategies_repo=strategies)
    assert job is not None
    assert job["force"] is True


@pytest.mark.asyncio
async def test_run_learning_job_creates_versioned_digest_with_mocked_llm():
    sid = "s-run"
    await _seed_outcomes(sid, n_wins=3, n_losses=3)
    strategies = AsyncMock()
    strategies.get_by_id = AsyncMock(return_value=_strategy_doc(sid, learn_enabled=True))
    models = AsyncMock()
    models.find_enabled_by_id = AsyncMock(return_value=_enabled_model())

    job = await queue_learning_job(sid, strategies_repo=strategies)
    assert job is not None

    learn_json = (
        '{"standing_rules":["Hold winners through London"],'
        '"anti_rules":["No late-NY fade"],'
        '"summary":"London continuation bias."}'
    )
    with patch(
        "brokerai.ai_strategy.learning.analyze_with_model",
        new_callable=AsyncMock,
        return_value=learn_json,
    ) as mock_llm:
        result = await run_learning_job(
            job["id"],
            strategies_repo=strategies,
            models_repo=models,
        )
        mock_llm.assert_awaited_once()
        kwargs = mock_llm.await_args.kwargs
        assert kwargs["cost_context"]["operation"] == "strategy_learn"
        assert kwargs["cost_context"]["billable"] is True
        assert kwargs["cost_context"]["strategy_id"] == sid
        messages = mock_llm.await_args.args[3]
        user = messages[1]["content"]
        assert "Win sample" in user
        assert "Loss sample" in user

    assert result["status"] == LEARNING_JOB_STATUS_COMPLETED
    digest = await StrategyMemoryDigestsRepository().get_latest(sid)
    assert digest is not None
    assert digest["version"] == 1
    standing_texts = [r["text"] if isinstance(r, dict) else r for r in digest["standing_rules"]]
    anti_texts = [r["text"] if isinstance(r, dict) else r for r in digest["anti_rules"]]
    assert "Hold winners through London" in standing_texts
    assert "No late-NY fade" in anti_texts
    assert digest["covered_through"]

    # Below threshold after coverage → no new job
    no_job = await queue_learning_job(sid, strategies_repo=strategies)
    assert no_job is None

    # Second batch versions digest
    await _seed_outcomes(
        sid,
        n_wins=3,
        n_losses=2,
        base=datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc),
    )
    job2 = await queue_learning_job(sid, strategies_repo=strategies)
    assert job2 is not None
    with patch(
        "brokerai.ai_strategy.learning.analyze_with_model",
        new_callable=AsyncMock,
        return_value=(
            '{"standing_rules":["Keep London bias"],'
            '"anti_rules":["Avoid chase"],'
            '"summary":"v2"}'
        ),
    ):
        await run_learning_job(
            job2["id"],
            strategies_repo=strategies,
            models_repo=models,
        )
    digest2 = await StrategyMemoryDigestsRepository().get_latest(sid)
    assert digest2 is not None
    assert digest2["version"] == 2


@pytest.mark.asyncio
async def test_close_shadow_lot_queues_but_does_not_run_llm():
    sid = "s-close"
    strategies = AsyncMock()
    strategies.get_by_id = AsyncMock(return_value=_strategy_doc(sid, learn_enabled=True))

    # Pre-seed 4 outcomes so the 5th close hits threshold.
    await _seed_outcomes(sid, n_wins=2, n_losses=2)
    lot = {
        "id": "lot-1",
        "strategy_id": sid,
        "pair": "EUR/USD",
        "timeframe": "M15",
        "direction": "long",
        "entry_price": 1.1000,
        "units": 1000,
        "state": "open",
        "opened_at": datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc).isoformat(),
    }
    from brokerai.db.repositories.shadow_trading import ShadowLotsRepository

    await ShadowLotsRepository().upsert_lot(lot)

    with (
        patch(
            "brokerai.ai_strategy.learning.StrategiesRepository",
            return_value=strategies,
        ),
        patch(
            "brokerai.ai_strategy.learning.analyze_with_model",
            new_callable=AsyncMock,
        ) as mock_llm,
    ):
        closed = await close_shadow_lot_with_outcome(
            lot, exit_price=1.1010, exit_reason="take_profit"
        )
        mock_llm.assert_not_called()

    assert closed is not None
    assert closed["state"] == "closed"
    open_jobs = await LearningJobsRepository().list_queued()
    assert any(j["strategy_id"] == sid for j in open_jobs)


@pytest.mark.asyncio
async def test_load_weekly_bot_results_summarizes_outcomes():
    sid = "s-week"
    week_start = date(2026, 7, 20)  # Monday
    week_end = date(2026, 7, 24)  # Friday
    await _seed_outcomes(
        sid,
        n_wins=2,
        n_losses=1,
        base=datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc),
    )
    text = await load_weekly_bot_results(week_start, week_end)
    assert text is not None
    assert "Closed trades: 3" in text
    assert "wins=2" in text
    assert "losses=1" in text
    assert "shadow=3" in text

    empty = await load_weekly_bot_results(date(2026, 1, 5), date(2026, 1, 9))
    assert empty is None


@pytest.mark.asyncio
async def test_runtime_prompt_includes_digest():
    sid = "s-prompt"
    await StrategyMemoryDigestsRepository().create_version(
        sid,
        {
            "standing_rules": ["Favor pullbacks in trend"],
            "anti_rules": ["No news spikes"],
            "summary": "Trend pullback playbook",
            "covered_through": datetime(2026, 7, 20, tzinfo=timezone.utc).isoformat(),
        },
        version=1,
    )
    preset = get_preset("ai_strategy")
    assert preset is not None
    params = prepare_params(
        preset,
        {
            "schema_version": 1,
            "timeframe": "M15",
            "ai": {
                "llm_mode": "interval",
                "model_id": "model-1",
                "min_llm_interval_minutes": 15,
                "max_context_bars": 32,
            },
        },
    )
    candles = generate_mock_candles(80)
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [params])
    evaluator = ModelSignalRuntime()
    decision_json = (
        '{"action":"hold","direction":null,"confidence":0.4,'
        '"thesis":"wait","invalidation":"na"}'
    )
    with (
        patch(
            "brokerai.trading.presets.ai_strategy.runtime.AiModelsRepository"
        ) as mock_repo_cls,
        patch(
            "brokerai.trading.presets.ai_strategy.runtime.StrategyGuidanceRepository"
        ) as mock_guidance_cls,
        patch(
            "brokerai.trading.presets.ai_strategy.runtime.analyze_with_model",
            new_callable=AsyncMock,
            return_value=decision_json,
        ) as mock_llm,
    ):
        mock_repo_cls.return_value.find_enabled_by_id = AsyncMock(
            return_value=_enabled_model()
        )
        mock_guidance_cls.return_value.get_for_symbol = AsyncMock(return_value=None)
        await evaluator.evaluate_async(
            candles, params, cache, strategy_id=sid, pair="EUR/USD"
        )
        mock_llm.assert_awaited_once()
        user = mock_llm.await_args.args[3][1]["content"]
        assert "Memory digest v1" in user
        assert "Favor pullbacks in trend" in user
        assert "No news spikes" in user
