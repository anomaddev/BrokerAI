import { describe, expect, it } from "vitest";
import {
  candleLookbackMinutes,
  computeBuilderMinCandles,
  formatCandleLookback,
  formatDurationMinutes,
  roundUpMinCandles,
} from "./helpers";

describe("roundUpMinCandles", () => {
  it("rounds up to the nearest 10", () => {
    expect(roundUpMinCandles(63)).toBe(70);
    expect(roundUpMinCandles(70)).toBe(70);
    expect(roundUpMinCandles(21)).toBe(30);
    expect(roundUpMinCandles(20)).toBe(20);
  });

  it("applies when computing builder minimum candles", () => {
    expect(
      computeBuilderMinCandles({
        fastEma: 9,
        slowEma: 21,
      }),
    ).toBe(70);
  });
});

describe("candle lookback duration", () => {
  it("computes minutes from timeframe × candle count", () => {
    expect(candleLookbackMinutes("M15", 50)).toBe(750);
    expect(candleLookbackMinutes("H1", 24)).toBe(1_440);
    expect(candleLookbackMinutes("D1", 7)).toBe(10_080);
  });

  it("formats whole-unit durations", () => {
    expect(formatDurationMinutes(5)).toBe("5 minutes");
    expect(formatDurationMinutes(60)).toBe("1 hour");
    expect(formatDurationMinutes(300)).toBe("5 hours");
    expect(formatDurationMinutes(1_440)).toBe("1 day");
    expect(formatDurationMinutes(10_080)).toBe("1 week");
    expect(formatDurationMinutes(43_200)).toBe("1 month");
  });

  it("formats fractional durations to one decimal", () => {
    expect(formatDurationMinutes(90)).toBe("1.5 hours");
    expect(formatCandleLookback("M15", 50)).toBe("12.5 hours");
  });
});
