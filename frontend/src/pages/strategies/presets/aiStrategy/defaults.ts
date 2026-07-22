import type { Timeframe } from "../../../../lib/strategyParams";
import { TIMEFRAME_OPTIONS } from "../../../../lib/strategyParams";

export type AiLlmMode = "off" | "on_signal_change" | "interval" | "manual";

export type AiStrategyParams = {
  timeframe: Timeframe;
  /** Warm-up / lookback bars before the strategy runs (maps to params.min_candles). */
  minCandles: number;
  /** Context window for AI guidance (maps to params.ai.max_context_bars). */
  maxContextBars: number;
  useDailyReport: boolean;
  useWeeklyBrief: boolean;
  useWeeklyDebrief: boolean;
  /** Slice 1 always persists Off; UI shows it disabled. */
  llmMode: AiLlmMode;
  sessions: string[];
  riskPerTrade: number;
  maxTradesPerDay: number;
  minConfidence: number;
};

export const AI_LOOKBACK_MIN = 16;
export const AI_LOOKBACK_MAX = 500;

export const DEFAULT_AI_STRATEGY_PARAMS: AiStrategyParams = {
  timeframe: "M15",
  minCandles: 64,
  maxContextBars: 64,
  useDailyReport: true,
  useWeeklyBrief: true,
  useWeeklyDebrief: true,
  llmMode: "off",
  sessions: ["London", "NY"],
  riskPerTrade: 1.0,
  maxTradesPerDay: 3,
  minConfidence: 60,
};

export { TIMEFRAME_OPTIONS };
