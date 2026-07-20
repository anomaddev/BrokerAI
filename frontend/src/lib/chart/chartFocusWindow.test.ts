import { describe, expect, it } from "vitest";
import type { CandleBar } from "../../api/client";
import {
  FOCUS_VISIBLE_BARS,
  buildCenteredBarFocusWindow,
  chartFocusVisibleLogicalRange,
  extendCandlesForWarmup,
  findCandleIndexNearUnix,
  sliceCandlesAroundUnix,
} from "./chartFocusWindow";

function bar(iso: string): CandleBar {
  return {
    time: iso,
    open: 1,
    high: 1,
    low: 1,
    close: 1,
    volume: 0,
  };
}

function makeBars(count: number, startMs: number, stepMs: number): CandleBar[] {
  return Array.from({ length: count }, (_, index) =>
    bar(new Date(startMs + index * stepMs).toISOString()),
  );
}

describe("sliceCandlesAroundUnix", () => {
  it("returns all bars when under the cap", () => {
    const bars = makeBars(10, Date.parse("2026-01-01T00:00:00.000Z"), 60_000);
    expect(sliceCandlesAroundUnix(bars, Date.parse("2026-01-01T00:05:00.000Z") / 1000, 50)).toHaveLength(
      10,
    );
  });

  it("caps a long series around the center", () => {
    const step = 60_000;
    const start = Date.parse("2026-01-01T00:00:00.000Z");
    const bars = makeBars(5000, start, step);
    const centerUnix = Math.floor((start + 2500 * step) / 1000);
    const sliced = sliceCandlesAroundUnix(bars, centerUnix, 200);
    expect(sliced).toHaveLength(200);
    const mid = sliced[Math.floor(sliced.length / 2)];
    const midUnix = Math.floor(Date.parse(mid.time) / 1000);
    expect(Math.abs(midUnix - centerUnix)).toBeLessThanOrEqual(step / 1000);
  });
});

describe("findCandleIndexNearUnix", () => {
  it("finds the last bar at or before the target", () => {
    const bars = makeBars(5, Date.parse("2026-01-01T00:00:00.000Z"), 60_000);
    const idx = findCandleIndexNearUnix(
      bars,
      Math.floor(Date.parse("2026-01-01T00:02:30.000Z") / 1000),
    );
    expect(idx).toBe(2);
  });
});

describe("extendCandlesForWarmup", () => {
  it("prepends history before the window", () => {
    const all = makeBars(20, Date.parse("2026-01-01T00:00:00.000Z"), 60_000);
    const window = all.slice(10, 15);
    const extended = extendCandlesForWarmup(all, window, 5);
    expect(extended).toHaveLength(10);
    expect(extended[0].time).toBe(all[5].time);
    expect(extended[extended.length - 1].time).toBe(window[window.length - 1].time);
  });
});

describe("buildCenteredBarFocusWindow", () => {
  it("pads the visible window by bars for the timeframe", () => {
    const anchor = "2026-07-20T18:00:00.000Z";
    const center = Date.parse(anchor);
    const window = buildCenteredBarFocusWindow({
      anchorIso: anchor,
      timeframe: "M15",
      displaySinceMs: center - 7 * 86_400_000,
      displayUntilMs: center + 86_400_000,
    });
    expect(window).not.toBeNull();
    const spanSec = (window!.visibleToTime - window!.visibleFromTime);
    // 80 bars * 15 minutes = 20 hours total (±40 bars)
    expect(spanSec).toBe(FOCUS_VISIBLE_BARS * 15 * 60);
  });

  it("keeps readable context on daily bars (not 1–2 candles)", () => {
    const anchor = "2026-07-20T00:00:00.000Z";
    const center = Date.parse(anchor);
    const window = buildCenteredBarFocusWindow({
      anchorIso: anchor,
      timeframe: "D1",
      displaySinceMs: center - 365 * 86_400_000,
      displayUntilMs: center + 30 * 86_400_000,
      visibleBars: 80,
    });
    expect(window).not.toBeNull();
    const spanDays = (window!.visibleToTime - window!.visibleFromTime) / 86_400;
    expect(spanDays).toBe(80);
  });
});

describe("chartFocusVisibleLogicalRange", () => {
  it("centers a fixed bar span on the anchor candle", () => {
    const step = 900_000;
    const start = Date.parse("2026-07-20T00:00:00.000Z");
    const bars = makeBars(200, start, step);
    const anchorIdx = 100;
    const centerUnix = Math.floor((start + anchorIdx * step) / 1000);
    const logical = chartFocusVisibleLogicalRange(
      bars,
      { visibleFromTime: centerUnix - 1000, visibleToTime: centerUnix + 1000 },
      80,
    );
    expect(logical).not.toBeNull();
    expect(logical!.to - logical!.from).toBe(80);
    expect(Math.round((logical!.from + logical!.to) / 2)).toBe(anchorIdx);
  });
});
