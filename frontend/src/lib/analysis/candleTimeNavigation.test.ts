import { describe, expect, it } from "vitest";
import type { CandleTimeSummary } from "./candleTimeSummaries";
import {
  buildCandleNavKeys,
  resolveCandleNeighbors,
  resolveCurrentCandleKey,
} from "./candleTimeNavigation";

function summary(
  key: string,
  overrides: Partial<CandleTimeSummary> = {},
): CandleTimeSummary {
  return {
    key,
    label: key,
    sources: [],
    timeframes: [],
    assetClasses: [],
    strategyCount: 0,
    runCount: 0,
    exitMonitorTradeCount: 0,
    isCurrentBar: false,
    ...overrides,
  };
}

describe("candleTimeNavigation", () => {
  const summaries = [
    summary("c2", { isCurrentBar: true }),
    summary("c1"),
    summary("c0"),
  ];

  it("builds ordered candle keys from summaries", () => {
    expect(buildCandleNavKeys(summaries)).toEqual(["c2", "c1", "c0"]);
  });

  it("resolves neighbors within the candle list", () => {
    const keys = buildCandleNavKeys(summaries);
    expect(resolveCandleNeighbors(keys, "c1")).toEqual({
      previousKey: "c2",
      nextKey: "c0",
      index: 1,
      total: 3,
    });
    expect(resolveCandleNeighbors(keys, "missing").index).toBe(-1);
  });

  it("prefers the current-bar candle key", () => {
    expect(resolveCurrentCandleKey(summaries)).toBe("c2");
    expect(resolveCurrentCandleKey([summary("c0")])).toBe("c0");
    expect(resolveCurrentCandleKey([])).toBeNull();
  });
});
