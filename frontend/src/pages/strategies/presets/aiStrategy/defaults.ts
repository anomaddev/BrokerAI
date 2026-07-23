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
  /** Bound API source id from Settings → Models (null until selected). */
  modelId: string | null;
  /** Catalog model name from the selected source (null until selected). */
  modelName: string | null;
  llmMode: AiLlmMode;
  /** Outcome → memory digest learning + daily improve eligibility. */
  learnEnabled: boolean;
  sessions: string[];
  riskPerTrade: number;
  maxTradesPerDay: number;
  minConfidence: number;
};

export const AI_LOOKBACK_MIN = 15;
export const AI_LOOKBACK_MAX = 500;
export const AI_LOOKBACK_STEP = 5;

export const LLM_MODE_OPTIONS: { value: AiLlmMode; label: string }[] = [
  { value: "off", label: "Off" },
  { value: "interval", label: "Interval (throttled)" },
  { value: "on_signal_change", label: "On signal change" },
  { value: "manual", label: "Manual" },
];

export const DEFAULT_AI_STRATEGY_PARAMS: AiStrategyParams = {
  timeframe: "M15",
  minCandles: 200,
  maxContextBars: 200,
  useDailyReport: true,
  useWeeklyBrief: true,
  useWeeklyDebrief: true,
  modelId: null,
  modelName: null,
  llmMode: "off",
  learnEnabled: true,
  sessions: ["London", "NY"],
  riskPerTrade: 1.0,
  maxTradesPerDay: 3,
  minConfidence: 60,
};

export { TIMEFRAME_OPTIONS };
