import type { Timeframe } from "./strategyParams/types";

/** Keep in sync with backend `candle_schedule.CLOSE_BUFFER`. */
export const CLOSE_BUFFER_MS = 3000;

const EPOCH_MS = Date.UTC(1970, 0, 1);

const TIMEFRAME_MS: Record<Timeframe, number> = {
  M1: 60_000,
  M2: 120_000,
  M3: 180_000,
  M4: 240_000,
  M5: 300_000,
  M10: 600_000,
  M15: 900_000,
  M30: 1_800_000,
  H1: 3_600_000,
  H2: 7_200_000,
  H3: 10_800_000,
  H4: 14_400_000,
  H6: 21_600_000,
  H8: 28_800_000,
  H12: 43_200_000,
  D1: 86_400_000,
  W1: 604_800_000,
  MN: 2_592_000_000,
};

export function timeframeToMs(timeframe: Timeframe): number {
  return TIMEFRAME_MS[timeframe];
}

export function isKnownTimeframe(value: string): value is Timeframe {
  return value in TIMEFRAME_MS;
}

/** Mirror backend `next_candle_close_at` — UTC boundary + close buffer. */
export function nextCandleCloseAtMs(nowMs: number, timeframe: Timeframe): number {
  const durationMs = timeframeToMs(timeframe);
  const elapsed = nowMs - EPOCH_MS;
  const nextBoundary = EPOCH_MS + Math.ceil(elapsed / durationMs) * durationMs;
  return nextBoundary + CLOSE_BUFFER_MS;
}

export function candleWindowStartAtMs(targetAtMs: number, timeframe: Timeframe): number {
  return targetAtMs - timeframeToMs(timeframe);
}
