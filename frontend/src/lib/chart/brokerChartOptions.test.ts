import { describe, expect, it } from "vitest";
import {
  MAX_VISIBLE_CANDLES,
  initialVisibleLogicalRange,
} from "./brokerChartOptions";

describe("initialVisibleLogicalRange", () => {
  it("shows all bars when count is below the cap", () => {
    expect(initialVisibleLogicalRange(50)).toEqual({ from: 0, to: 49 });
  });

  it("shows the most recent capped bars when data exceeds the cap", () => {
    const range = initialVisibleLogicalRange(200);
    expect(range).toEqual({ from: 120, to: 199 });
    expect(range.to - range.from + 1).toBe(MAX_VISIBLE_CANDLES);
  });

  it("returns zero range for empty data", () => {
    expect(initialVisibleLogicalRange(0)).toEqual({ from: 0, to: 0 });
  });
});
