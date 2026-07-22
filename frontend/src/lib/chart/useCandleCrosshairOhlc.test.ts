import { describe, expect, it } from "vitest";
import type { UTCTimestamp } from "lightweight-charts";
import type { CandleBar } from "../../api/client";
import { defaultOhlcSnapshot, ohlcSnapshotsEqual } from "./useCandleCrosshairOhlc";

function bar(iso: string, close = 1): CandleBar {
  return {
    time: iso,
    open: close,
    high: close,
    low: close,
    close,
    volume: 0,
  };
}

describe("ohlcSnapshotsEqual", () => {
  it("treats identical OHLC values as equal even across object identity", () => {
    const a = {
      time: 1 as UTCTimestamp,
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.5,
    };
    const b = { ...a };
    expect(ohlcSnapshotsEqual(a, b)).toBe(true);
    expect(ohlcSnapshotsEqual(a, { ...a, close: 1.6 })).toBe(false);
    expect(ohlcSnapshotsEqual(null, null)).toBe(true);
    expect(ohlcSnapshotsEqual(a, null)).toBe(false);
  });
});

describe("defaultOhlcSnapshot", () => {
  it("uses the last candle when no focus center is set", () => {
    const candles = [
      bar("2026-01-20T00:00:00.000Z", 1),
      bar("2026-02-17T15:45:00.000Z", 2),
    ];
    const snapshot = defaultOhlcSnapshot(candles, null);
    expect(snapshot?.close).toBe(2);
    expect(snapshot?.time).toBe(Math.floor(Date.parse("2026-02-17T15:45:00.000Z") / 1000));
  });

  it("uses the candle nearest the focus center when focused", () => {
    const candles = [
      bar("2026-01-20T08:30:00.000Z", 10),
      bar("2026-01-20T08:45:00.000Z", 11),
      bar("2026-02-17T15:45:00.000Z", 99),
    ];
    const center = Math.floor(Date.parse("2026-01-20T08:30:00.000Z") / 1000);
    const snapshot = defaultOhlcSnapshot(candles, center);
    expect(snapshot?.close).toBe(10);
    expect(snapshot?.time).toBe(center);
  });
});
