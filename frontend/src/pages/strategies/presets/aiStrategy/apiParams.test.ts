import { describe, expect, it } from "vitest";
import { aiStrategyParamsToV1, v1ToAiStrategyParams } from "./apiParams";
import { DEFAULT_AI_STRATEGY_PARAMS } from "./defaults";

describe("aiStrategy apiParams", () => {
  it("round-trips defaults with ai section", () => {
    const v1 = aiStrategyParamsToV1(DEFAULT_AI_STRATEGY_PARAMS);
    expect(v1.signal.type).toBe("ai_strategy");
    expect(v1.ai?.llm_mode).toBe("off");
    expect(v1.ai?.use_daily_report).toBe(true);
    expect(v1.min_candles).toBe(64);
    expect(v1.ai?.max_context_bars).toBe(64);

    const back = v1ToAiStrategyParams(v1);
    expect(back.timeframe).toBe("M15");
    expect(back.useDailyReport).toBe(true);
    expect(back.llmMode).toBe("off");
    expect(back.maxContextBars).toBe(64);
  });

  it("forces llm_mode off on save even if UI had another mode", () => {
    const v1 = aiStrategyParamsToV1({
      ...DEFAULT_AI_STRATEGY_PARAMS,
      llmMode: "interval",
      useWeeklyBrief: false,
      maxContextBars: 120,
      minCandles: 120,
    });
    expect(v1.ai?.llm_mode).toBe("off");
    expect(v1.ai?.use_weekly_brief).toBe(false);
    expect(v1.ai?.max_context_bars).toBe(120);
    expect(v1.min_candles).toBe(120);
  });
});
