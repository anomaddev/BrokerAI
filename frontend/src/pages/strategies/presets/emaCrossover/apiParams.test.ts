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
});
