import { describe, expect, it } from "vitest";
import { DEFAULT_EMA_CROSSOVER_PARAMS } from "./defaults";
import { emaCrossoverParamsToV1, v1ToEmaCrossoverParams } from "./apiParams";

describe("v1ToEmaCrossoverParams", () => {
  it("round-trips fixed_pips_jpy and defaults ATR stop-loss mode", () => {
    expect(DEFAULT_EMA_CROSSOVER_PARAMS.stopLossType).toBe("atr_based");
    expect(DEFAULT_EMA_CROSSOVER_PARAMS.slFixedPipsJpy).toBe(50);

    const v1 = emaCrossoverParamsToV1({
      ...DEFAULT_EMA_CROSSOVER_PARAMS,
      stopLossType: "fixed_pips",
      slFixedPips: 20,
      slFixedPipsJpy: 75,
    });
    expect(v1.exits.stop_loss.fixed_pips).toBe(20);
    expect(v1.exits.stop_loss.fixed_pips_jpy).toBe(75);

    const hydrated = v1ToEmaCrossoverParams(v1);
    expect(hydrated.slFixedPips).toBe(20);
    expect(hydrated.slFixedPipsJpy).toBe(75);
  });

  it("falls back to 50 when fixed_pips_jpy is missing", () => {
    const v1 = emaCrossoverParamsToV1(DEFAULT_EMA_CROSSOVER_PARAMS);
    delete v1.exits.stop_loss.fixed_pips_jpy;
    const hydrated = v1ToEmaCrossoverParams(v1);
    expect(hydrated.slFixedPipsJpy).toBe(50);
  });

  it("enables ADX/ATR chart overlays when filters are enabled", () => {
    const v1 = emaCrossoverParamsToV1(DEFAULT_EMA_CROSSOVER_PARAMS);
    const params = v1ToEmaCrossoverParams(v1);

    expect(params.adxFilter).toBe(true);
    expect(params.atrFilter).toBe(true);
    expect(params.overlays.adx).toBe(true);
    expect(params.overlays.atr).toBe(true);
    expect(params.overlayMode).toBe("detailed");
  });

  it("disables ADX/ATR chart overlays when filters are disabled", () => {
    const v1 = emaCrossoverParamsToV1({
      ...DEFAULT_EMA_CROSSOVER_PARAMS,
      adxFilter: false,
      atrFilter: false,
    });
    const params = v1ToEmaCrossoverParams(v1);

    expect(params.overlays.adx).toBe(false);
    expect(params.overlays.atr).toBe(false);
  });

  it("round-trips reverse_crossover exit protection settings", () => {
    const v1 = emaCrossoverParamsToV1({
      ...DEFAULT_EMA_CROSSOVER_PARAMS,
      reverseCrossoverEnabled: true,
      reverseCrossoverMinBarsAfterEntry: 8,
      reverseCrossoverMinConfirmationBars: 3,
      reverseCrossoverMinSeparationAtr: 0.35,
    });
    expect(v1.exits.reverse_crossover).toEqual({
      enabled: true,
      min_bars_after_entry: 8,
      min_confirmation_bars: 3,
      min_separation_atr: 0.35,
    });

    const hydrated = v1ToEmaCrossoverParams(v1);
    expect(hydrated.reverseCrossoverEnabled).toBe(true);
    expect(hydrated.reverseCrossoverMinBarsAfterEntry).toBe(8);
    expect(hydrated.reverseCrossoverMinConfirmationBars).toBe(3);
    expect(hydrated.reverseCrossoverMinSeparationAtr).toBe(0.35);
  });

  it("defaults reverse_crossover settings when omitted from v1", () => {
    const v1 = emaCrossoverParamsToV1(DEFAULT_EMA_CROSSOVER_PARAMS);
    delete v1.exits.reverse_crossover;
    const hydrated = v1ToEmaCrossoverParams(v1);
    expect(hydrated.reverseCrossoverEnabled).toBe(true);
    expect(hydrated.reverseCrossoverMinBarsAfterEntry).toBe(6);
    expect(hydrated.reverseCrossoverMinConfirmationBars).toBe(2);
    expect(hydrated.reverseCrossoverMinSeparationAtr).toBe(0.2);
  });

  it("round-trips approaching, post-stop cooldown, and HTF bias", () => {
    const v1 = emaCrossoverParamsToV1({
      ...DEFAULT_EMA_CROSSOVER_PARAMS,
      approachingEnabled: false,
      approachingMaxGapAtr: 0.35,
      approachingMinNarrowBars: 3,
      postStopCooldownBars: 8,
      htfBiasEnabled: true,
      htfBiasTimeframe: "H1",
      minAtr: 0.0008,
      minAtrJpy: 0.05,
    });

    expect(v1.signal.type).toBe("ema_crossover");
    if (v1.signal.type === "ema_crossover") {
      expect(v1.signal.approaching).toEqual({
        enabled: false,
        max_gap_atr: 0.35,
        min_narrow_bars: 3,
      });
    }
    expect(v1.execution.post_stop_cooldown_bars).toBe(8);
    expect(v1.filters.some((f) => f.type === "htf_bias" && f.enabled)).toBe(true);
    const atr = v1.filters.find((f) => f.type === "atr");
    expect(atr && "min_value" in atr ? atr.min_value : null).toBe(0.0008);
    expect(atr && "min_value_jpy" in atr ? atr.min_value_jpy : null).toBe(0.05);

    const hydrated = v1ToEmaCrossoverParams(v1);
    expect(hydrated.approachingEnabled).toBe(false);
    expect(hydrated.approachingMaxGapAtr).toBe(0.35);
    expect(hydrated.approachingMinNarrowBars).toBe(3);
    expect(hydrated.postStopCooldownBars).toBe(8);
    expect(hydrated.htfBiasEnabled).toBe(true);
    expect(hydrated.htfBiasTimeframe).toBe("H1");
    expect(hydrated.minAtr).toBe(0.0008);
    expect(hydrated.minAtrJpy).toBe(0.05);
  });
});
