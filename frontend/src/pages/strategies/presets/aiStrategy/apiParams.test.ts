import { describe, expect, it } from "vitest";
import { aiStrategyParamsToV1, v1ToAiStrategyParams } from "./apiParams";
import { DEFAULT_AI_STRATEGY_PARAMS } from "./defaults";

describe("aiStrategy apiParams", () => {
  it("round-trips defaults with ai section", () => {
    const v1 = aiStrategyParamsToV1(DEFAULT_AI_STRATEGY_PARAMS);
    expect(v1.signal.type).toBe("ai_strategy");
    expect(v1.ai?.llm_mode).toBe("off");
    expect(v1.ai?.learn_enabled).toBe(true);
    expect(v1.ai?.use_daily_report).toBe(true);
    expect(v1.min_candles).toBe(200);
    expect(v1.ai?.max_context_bars).toBe(200);

    const back = v1ToAiStrategyParams(v1);
    expect(back.timeframe).toBe("M15");
    expect(back.useDailyReport).toBe(true);
    expect(back.llmMode).toBe("off");
    expect(back.learnEnabled).toBe(true);
    expect(back.maxContextBars).toBe(200);
  });

  it("snaps lookback to multiples of 5", () => {
    const v1 = aiStrategyParamsToV1({
      ...DEFAULT_AI_STRATEGY_PARAMS,
      maxContextBars: 64,
      minCandles: 64,
    });
    expect(v1.ai?.max_context_bars).toBe(65);
    expect(v1.min_candles).toBe(65);

    const back = v1ToAiStrategyParams({
      ...v1,
      min_candles: 17,
      ai: { ...v1.ai, max_context_bars: 17 },
    });
    expect(back.maxContextBars).toBe(15);
    expect(back.minCandles).toBe(15);
  });

  it("persists llm_mode, model_id, model_name, and learn_enabled from UI", () => {
    const v1 = aiStrategyParamsToV1({
      ...DEFAULT_AI_STRATEGY_PARAMS,
      llmMode: "interval",
      modelId: "model-abc",
      modelName: "gpt-test",
      learnEnabled: true,
      useWeeklyBrief: false,
      maxContextBars: 120,
      minCandles: 120,
    });
    expect(v1.ai?.llm_mode).toBe("interval");
    expect(v1.ai?.model_id).toBe("model-abc");
    expect(v1.ai?.model_name).toBe("gpt-test");
    expect(v1.ai?.learn_enabled).toBe(true);
    expect(v1.ai?.use_weekly_brief).toBe(false);
    expect(v1.ai?.max_context_bars).toBe(120);
    expect(v1.min_candles).toBe(120);

    const back = v1ToAiStrategyParams(v1);
    expect(back.llmMode).toBe("interval");
    expect(back.modelId).toBe("model-abc");
    expect(back.modelName).toBe("gpt-test");
    expect(back.learnEnabled).toBe(true);
  });
});
