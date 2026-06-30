import { TIMEFRAME_LABELS, TIMEFRAMES, type Timeframe } from "./strategyParams";

/** OANDA-supported granularities (excludes M3 which has no OANDA mapping). */
export const EXPLORE_TIMEFRAMES: Timeframe[] = TIMEFRAMES.filter(
  (tf) => tf !== "M3",
);

export const EXPLORE_TIMEFRAME_OPTIONS = EXPLORE_TIMEFRAMES.map((value) => ({
  value,
  label: TIMEFRAME_LABELS[value],
}));

export const HISTORY_DURATIONS = ["1D", "1W", "1M", "3M", "6M"] as const;
export type HistoryDuration = (typeof HISTORY_DURATIONS)[number];

export const DEFAULT_HISTORY_DURATION: HistoryDuration = "1W";
export const DEFAULT_TIMEFRAME: Timeframe = "M15";

/** Matches backend CANDLE_LIMIT_MAX after plan update. */
export const CANDLE_LIMIT_MAX = 2000;
export const CANDLE_LIMIT_MIN = 50;

export const HISTORY_DURATION_OPTIONS = HISTORY_DURATIONS.map((value) => ({
  value,
  label: value,
}));

const MINUTES_PER_TIMEFRAME: Record<Timeframe, number> = {
  M1: 1,
  M2: 2,
  M3: 3,
  M4: 4,
  M5: 5,
  M10: 10,
  M15: 15,
  M30: 30,
  H1: 60,
  H2: 120,
  H3: 180,
  H4: 240,
  H6: 360,
  H8: 480,
  H12: 720,
  D1: 1440,
  W1: 10080,
  MN: 43200,
};

/** Approximate forex trading minutes per calendar period (24/5). */
const TRADING_MINUTES: Record<HistoryDuration, number> = {
  "1D": 1440,
  "1W": 7200,
  "1M": 30240,
  "3M": 90720,
  "6M": 181440,
};

export function parseExploreTimeframe(value: string | null): Timeframe {
  if (value && EXPLORE_TIMEFRAMES.includes(value as Timeframe)) {
    return value as Timeframe;
  }
  return DEFAULT_TIMEFRAME;
}

export function parseHistoryDuration(value: string | null): HistoryDuration {
  if (value && HISTORY_DURATIONS.includes(value as HistoryDuration)) {
    return value as HistoryDuration;
  }
  return DEFAULT_HISTORY_DURATION;
}

export function barsForHistoryDuration(
  timeframe: Timeframe,
  duration: HistoryDuration,
): number {
  const barMinutes = MINUTES_PER_TIMEFRAME[timeframe];
  const targetMinutes = TRADING_MINUTES[duration];
  const raw = Math.ceil(targetMinutes / barMinutes);
  return Math.max(CANDLE_LIMIT_MIN, Math.min(raw, CANDLE_LIMIT_MAX));
}

export function formatBarCountHint(count: number): string {
  return `~${count.toLocaleString()} bars`;
}
