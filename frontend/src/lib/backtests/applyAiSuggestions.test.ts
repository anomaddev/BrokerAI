import { describe, expect, it, beforeEach, afterEach } from "vitest";
import {
  applySuggestionsToParams,
  clearBacktestAiDraft,
  isAiStrategyDailyOrigin,
  loadBacktestAiDraft,
  storeBacktestAiDraft,
  suggestionDisplayValue,
} from "./applyAiSuggestions";
import type { StrategyParamsV1 } from "../strategyParams";

const baseParams = {
  schema_version: 1,
  timeframe: "M15",
  indicators: {
    fast: { type: "ema", period: 9, source: "close" },
    slow: { type: "ema", period: 21, source: "close" },
  },
  signal: {
    type: "ema_crossover",
    fast_ref: "fast",
    slow_ref: "slow",
    direction: "both",
    confirmation: "close",
    approaching: { enabled: true, max_gap_atr: 0.5, min_narrow_bars: 2 },
  },
  filters: [
    { id: "atr", type: "atr", enabled: true, period: 14, min_value: 0.0008 },
  ],
  exits: {
    stop_loss: { enabled: true, mode: "atr_based", atr_multiplier: 1.5 },
    take_profit: { enabled: true, mode: "rr_ratio", risk_reward_ratio: 2 },
  },
  risk: { risk_per_trade_pct: 1, max_trades_per_day: 3 },
  execution: {
    sessions: ["London"],
    min_confidence: 60,
    post_stop_cooldown_bars: 0,
  },
} as StrategyParamsV1;

describe("applySuggestionsToParams", () => {
  it("patches allowlisted filter and execution paths onto UI-backed fields", () => {
    const patched = applySuggestionsToParams(baseParams, [
      { id: "atr", path: "filters.atr.min_value", to: 0.05 },
      { id: "cd", path: "execution.post_stop_cooldown_bars", to: 6 },
      { id: "ap", path: "signal.approaching.enabled", to: false },
      { id: "htf", path: "filters.htf_bias.enabled", to: true },
      { id: "htf_tf", path: "filters.htf_bias.timeframe", to: "H1" },
    ]);

    const atr = patched.filters.find((f) => f.type === "atr");
    expect(atr && "min_value" in atr ? atr.min_value : null).toBe(0.05);
    expect(patched.execution.post_stop_cooldown_bars).toBe(6);
    expect(
      patched.signal.type === "ema_crossover" ? patched.signal.approaching?.enabled : null,
    ).toBe(false);
    const htf = patched.filters.find((f) => f.type === "htf_bias");
    expect(htf).toMatchObject({ enabled: true, timeframe: "H1" });
    expect(baseParams.execution.post_stop_cooldown_bars).toBe(0);
  });

  it("respects selectedIds when provided", () => {
    const patched = applySuggestionsToParams(
      baseParams,
      [
        { id: "a", path: "filters.atr.min_value", to: 0.05 },
        { id: "b", path: "risk.max_trades_per_day", to: 1 },
      ],
      new Set(["b"]),
    );
    const atr = patched.filters.find((f) => f.type === "atr");
    expect(atr && "min_value" in atr ? atr.min_value : null).toBe(0.0008);
    expect(patched.risk.max_trades_per_day).toBe(1);
  });

  it("does not patch params for ai_strategy_daily origin", () => {
    expect(isAiStrategyDailyOrigin("ai_strategy_daily")).toBe(true);
    const patched = applySuggestionsToParams(
      baseParams,
      [{ id: "atr", path: "filters.atr.min_value", to: 0.05 }],
      undefined,
      { origin: "ai_strategy_daily" },
    );
    const atr = patched.filters.find((f) => f.type === "atr");
    expect(atr && "min_value" in atr ? atr.min_value : null).toBe(0.0008);
  });
});

describe("backtest AI draft storage", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });
  afterEach(() => {
    sessionStorage.clear();
  });

  it("stores and loads a draft by run id", () => {
    storeBacktestAiDraft({
      runId: "run-1",
      strategyId: "strat-1",
      params: baseParams,
      appliedSuggestionIds: ["atr"],
      createdAt: new Date().toISOString(),
    });
    const loaded = loadBacktestAiDraft("run-1");
    expect(loaded?.strategyId).toBe("strat-1");
    expect(loaded?.appliedSuggestionIds).toEqual(["atr"]);
    clearBacktestAiDraft("run-1");
    expect(loadBacktestAiDraft("run-1")).toBeNull();
  });
});

describe("suggestionDisplayValue", () => {
  it("formats booleans and arrays", () => {
    expect(suggestionDisplayValue(true)).toBe("On");
    expect(suggestionDisplayValue(["London", "NY"])).toBe("London, NY");
  });
});
