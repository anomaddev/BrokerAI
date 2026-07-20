import { describe, expect, it } from "vitest";
import { DEFAULT_EMA_CROSSOVER_PARAMS } from "./defaults";
import {
  computeSlTpDistances,
  pipSizeForPair,
  previewPairFromSelection,
} from "./mockData";

describe("pipSizeForPair", () => {
  it("uses 0.01 for JPY quotes and 0.0001 otherwise", () => {
    expect(pipSizeForPair("USD/JPY")).toBe(0.01);
    expect(pipSizeForPair("EUR_JPY")).toBe(0.01);
    expect(pipSizeForPair("EUR/USD")).toBe(0.0001);
  });
});

describe("previewPairFromSelection", () => {
  it("returns the first instrument or EUR/USD", () => {
    expect(previewPairFromSelection(["USD/JPY", "EUR/USD"])).toBe("USD/JPY");
    expect(previewPairFromSelection([])).toBe("EUR/USD");
    expect(previewPairFromSelection(["*"])).toBe("EUR/USD");
  });
});

describe("computeSlTpDistances", () => {
  const candles = [
    { time: 1, open: 1.1, high: 1.11, low: 1.09, close: 1.1 },
    { time: 2, open: 1.1, high: 1.12, low: 1.08, close: 1.1 },
  ];
  const atr = 0.001;

  it("uses standard fixed pips for non-JPY preview pairs", () => {
    const params = {
      ...DEFAULT_EMA_CROSSOVER_PARAMS,
      stopLossType: "fixed_pips" as const,
      slFixedPips: 15,
      slFixedPipsJpy: 50,
      takeProfitType: "fixed_pips" as const,
      tpFixedPips: 30,
    };
    const { slDistance, tpDistance } = computeSlTpDistances(
      params,
      candles,
      atr,
      1.1,
      "EUR/USD",
    );
    expect(slDistance).toBeCloseTo(0.0015);
    expect(tpDistance).toBeCloseTo(0.003);
  });

  it("uses JPY fixed pips for JPY preview pairs", () => {
    const params = {
      ...DEFAULT_EMA_CROSSOVER_PARAMS,
      stopLossType: "fixed_pips" as const,
      slFixedPips: 15,
      slFixedPipsJpy: 50,
      takeProfitType: "fixed_pips" as const,
      tpFixedPips: 30,
    };
    const { slDistance, tpDistance } = computeSlTpDistances(
      params,
      candles,
      atr,
      150.0,
      "USD/JPY",
    );
    expect(slDistance).toBeCloseTo(0.5);
    expect(tpDistance).toBeCloseTo(0.3);
  });
});
