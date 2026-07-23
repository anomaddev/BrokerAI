import {
  SCHEMA_VERSION,
  TIMEFRAMES,
  type StrategyParamsV1,
  type Timeframe,
} from "../../../../lib/strategyParams";
import {
  AI_LOOKBACK_MAX,
  AI_LOOKBACK_MIN,
  AI_LOOKBACK_STEP,
  DEFAULT_AI_STRATEGY_PARAMS,
  type AiLlmMode,
  type AiStrategyParams,
} from "./defaults";

function normalizeTimeframe(v1: StrategyParamsV1): Timeframe {
  if (v1.timeframe && TIMEFRAMES.includes(v1.timeframe)) {
    return v1.timeframe;
  }
  return DEFAULT_AI_STRATEGY_PARAMS.timeframe;
}

function clampLookback(value: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  const snapped =
    AI_LOOKBACK_MIN +
    Math.round((Math.round(value) - AI_LOOKBACK_MIN) / AI_LOOKBACK_STEP) * AI_LOOKBACK_STEP;
  return Math.min(AI_LOOKBACK_MAX, Math.max(AI_LOOKBACK_MIN, snapped));
}

function normalizeLlmMode(raw: unknown): AiLlmMode {
  if (raw === "off" || raw === "on_signal_change" || raw === "interval" || raw === "manual") {
    return raw;
  }
  return "off";
}

/** Map builder UI state → StrategyParams v1 (including `ai` section). */
export function aiStrategyParamsToV1(params: AiStrategyParams): StrategyParamsV1 {
  const lookback = clampLookback(params.maxContextBars, DEFAULT_AI_STRATEGY_PARAMS.maxContextBars);
  const minCandles = clampLookback(params.minCandles, lookback);

  return {
    schema_version: SCHEMA_VERSION,
    timeframe: params.timeframe,
    min_candles: minCandles,
    indicators: {},
    signal: { type: "ai_strategy", mode: "scaffold" },
    filters: [],
    exits: {
      stop_loss: {
        enabled: true,
        mode: "atr_based",
        atr_multiplier: 1.5,
        fixed_pips: 15,
        fixed_pips_jpy: 50,
        structure_lookback: 10,
      },
      take_profit: {
        enabled: true,
        mode: "rr_ratio",
        risk_reward_ratio: 2.0,
        fixed_pips: 30,
        atr_multiplier: 2.5,
      },
    },
    risk: {
      risk_per_trade_pct: params.riskPerTrade,
      max_trades_per_day: params.maxTradesPerDay,
    },
    execution: {
      sessions: [...params.sessions],
      min_confidence: params.minConfidence,
      override_all_strategies: false,
      priority: 50,
      dont_hold_between_sessions: true,
      dont_hold_between_markets: true,
      close_before_market_hours: 2,
      no_late_market_trading: true,
      late_market_hours: 2,
      post_stop_cooldown_bars: 0,
    },
    ai: {
      model_id: params.modelId?.trim() || null,
      model_name: params.modelName?.trim() || null,
      use_daily_report: params.useDailyReport,
      use_weekly_brief: params.useWeeklyBrief,
      use_weekly_debrief: params.useWeeklyDebrief,
      llm_mode: params.llmMode,
      min_llm_interval_minutes: 240,
      max_llm_calls_per_day: 12,
      max_llm_calls_per_symbol_per_day: 4,
      max_context_bars: lookback,
      learn_enabled: params.learnEnabled,
    },
  };
}

/** Map StrategyParams v1 → builder UI state. */
export function v1ToAiStrategyParams(v1: StrategyParamsV1): AiStrategyParams {
  const ai = v1.ai;
  const lookback = clampLookback(
    ai?.max_context_bars ?? v1.min_candles ?? DEFAULT_AI_STRATEGY_PARAMS.maxContextBars,
    DEFAULT_AI_STRATEGY_PARAMS.maxContextBars,
  );
  const minCandles = clampLookback(
    v1.min_candles ?? lookback,
    DEFAULT_AI_STRATEGY_PARAMS.minCandles,
  );
  const modelRaw = ai?.model_id;
  const modelId =
    typeof modelRaw === "string" && modelRaw.trim() ? modelRaw.trim() : null;
  const modelNameRaw = ai?.model_name;
  const modelName =
    typeof modelNameRaw === "string" && modelNameRaw.trim() ? modelNameRaw.trim() : null;

  return {
    timeframe: normalizeTimeframe(v1),
    minCandles,
    maxContextBars: lookback,
    useDailyReport: ai?.use_daily_report ?? DEFAULT_AI_STRATEGY_PARAMS.useDailyReport,
    useWeeklyBrief: ai?.use_weekly_brief ?? DEFAULT_AI_STRATEGY_PARAMS.useWeeklyBrief,
    useWeeklyDebrief: ai?.use_weekly_debrief ?? DEFAULT_AI_STRATEGY_PARAMS.useWeeklyDebrief,
    modelId,
    modelName,
    llmMode: normalizeLlmMode(ai?.llm_mode),
    learnEnabled: ai?.learn_enabled ?? DEFAULT_AI_STRATEGY_PARAMS.learnEnabled,
    sessions:
      v1.execution.sessions.length > 0
        ? [...v1.execution.sessions]
        : [...DEFAULT_AI_STRATEGY_PARAMS.sessions],
    riskPerTrade: v1.risk.risk_per_trade_pct ?? DEFAULT_AI_STRATEGY_PARAMS.riskPerTrade,
    maxTradesPerDay: v1.risk.max_trades_per_day ?? DEFAULT_AI_STRATEGY_PARAMS.maxTradesPerDay,
    minConfidence: v1.execution.min_confidence ?? DEFAULT_AI_STRATEGY_PARAMS.minConfidence,
  };
}
