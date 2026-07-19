import { describe, expect, it } from "vitest";
import { DEFAULT_EMA_CROSSOVER_PARAMS } from "./defaults";
import { emaCrossoverParamsToV1, v1ToEmaCrossoverParams } from "./apiParams";

describe("v1ToEmaCrossoverParams", () => {
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
