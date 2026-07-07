from __future__ import annotations

from datetime import datetime

from brokerai.bots.data_manager.candle_requirements import required_candle_bars, strategy_params, strategy_timeframe
from brokerai.bots.data_manager.candles import OANDA_SOURCE
from brokerai.bots.data_manager.service import DataManagerService
from brokerai.db.repositories.strategy_analysis_runs import StrategyAnalysisRunsRepository
from brokerai.trading.ai_confirmation import maybe_confirm_trade_intent
from brokerai.trading.execution_gates import is_executor_eligible, passes_execution_gates, resolve_priority_conflicts
from brokerai.trading.types import AnalysisResult, TradeIntent


def serialize_intent(intent: TradeIntent | None) -> dict | None:
    if intent is None:
        return None
    return {
        "direction": intent.direction,
        "entry_price": intent.entry_price,
        "stop_loss": intent.stop_loss,
        "take_profit": intent.take_profit,
        "confidence": intent.confidence,
    }


async def record_execution_outcomes(
    analyses: list[AnalysisResult],
    strategies_by_id: dict[str, dict],
    *,
    trade_counts: dict,
    asset_enabled_sessions: list | None,
    when: datetime,
    open_pairs: set[str] | frozenset[str] | None = None,
    only_one_position_per_pair: bool = False,
) -> None:
    """Persist gate outcomes for analyses that will not enter intent dispatch."""
    for analysis in analyses:
        if not analysis.run_id or is_executor_eligible(analysis):
            continue
        strategy = strategies_by_id.get(analysis.strategy_id)
        if strategy is None:
            continue
        params = strategy_params(strategy)
        _passed, reasons, gate_details = passes_execution_gates(
            analysis,
            params,
            trade_counts,
            when=when,
            asset_enabled_sessions=asset_enabled_sessions,
            open_pairs=open_pairs,
            only_one_position_per_pair=only_one_position_per_pair,
        )
        await persist_execution_outcome(
            analysis,
            processed_at=when,
            gates_passed=False,
            gate_reasons=reasons,
            gate_details=gate_details,
            priority_winner=False,
            intent_queued=False,
            intent=None,
        )


async def persist_execution_outcome(
    analysis: AnalysisResult,
    *,
    processed_at: datetime,
    gates_passed: bool,
    gate_reasons: list[str],
    gate_details: dict | None = None,
    priority_winner: bool,
    intent_queued: bool,
    intent: TradeIntent | None,
) -> None:
    if not analysis.run_id:
        return
    execution = {
        "processed_at": processed_at.isoformat(),
        "gates_passed": gates_passed,
        "gate_reasons": gate_reasons,
        "gate_details": gate_details or {},
        "priority_winner": priority_winner,
        "intent_queued": intent_queued,
        "intent": serialize_intent(intent),
    }
    await StrategyAnalysisRunsRepository().update_execution(analysis.run_id, execution)


async def apply_execution_gates(
    analyses: list[AnalysisResult],
    strategies_by_id: dict[str, dict],
    *,
    trade_counts: dict,
    asset_enabled_sessions: list | None,
    when: datetime,
    data_manager: DataManagerService,
    open_pairs: set[str] | frozenset[str] | None = None,
    only_one_position_per_pair: bool = False,
) -> list[TradeIntent]:
    gated: list[tuple[AnalysisResult, dict, dict]] = []

    for analysis in analyses:
        if not is_executor_eligible(analysis):
            continue
        strategy = strategies_by_id.get(analysis.strategy_id)
        if strategy is None:
            continue
        params = strategy_params(strategy)
        passed, reasons, gate_details = passes_execution_gates(
            analysis,
            params,
            trade_counts,
            when=when,
            asset_enabled_sessions=asset_enabled_sessions,
            open_pairs=open_pairs,
            only_one_position_per_pair=only_one_position_per_pair,
        )
        if passed:
            gated.append((analysis, params, strategy))
        else:
            await persist_execution_outcome(
                analysis,
                processed_at=when,
                gates_passed=False,
                gate_reasons=reasons,
                gate_details=gate_details,
                priority_winner=False,
                intent_queued=False,
                intent=None,
            )

    winners = resolve_priority_conflicts([(analysis, params) for analysis, params, _ in gated])
    winner_ids = {(analysis.strategy_id, analysis.pair) for analysis, _ in winners}

    intents: list[TradeIntent] = []
    for analysis, params, strategy in gated:
        key = (analysis.strategy_id, analysis.pair)
        if key not in winner_ids:
            await persist_execution_outcome(
                analysis,
                processed_at=when,
                gates_passed=True,
                gate_reasons=[],
                gate_details={},
                priority_winner=False,
                intent_queued=False,
                intent=None,
            )
            continue

        timeframe = strategy_timeframe(strategy)
        candles: list[dict] = []
        if timeframe:
            candles = await data_manager.request_candles(
                analysis.pair,
                timeframe,
                bar_count=required_candle_bars(strategy),
                source=OANDA_SOURCE,
                requester="broker",
            )

        intent = await maybe_confirm_trade_intent(
            analysis,
            params,
            candles,
            asset_class="forex",
        )
        if intent is not None:
            intents.append(intent)

        await persist_execution_outcome(
            analysis,
            processed_at=when,
            gates_passed=True,
            gate_reasons=[],
            gate_details={},
            priority_winner=True,
            intent_queued=intent is not None,
            intent=intent,
        )

    return intents
