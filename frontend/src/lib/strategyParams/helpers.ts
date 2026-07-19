import type { FilterSpec, Timeframe } from "./types";

/** Allowed UI range for strategy min-candles (computed warmup may be higher). */
export const MIN_CANDLES_SLIDER_MIN = 20;
export const MIN_CANDLES_SLIDER_MAX = 2000;
export const MIN_CANDLES_STEP = 10;

/** Round up to the nearest step (default 10), clamped to the slider range. */
export function roundUpMinCandles(value: number, step = MIN_CANDLES_STEP): number {
  if (!Number.isFinite(value) || value <= 0) return MIN_CANDLES_SLIDER_MIN;
  const safeStep = step > 0 ? step : MIN_CANDLES_STEP;
  const rounded = Math.ceil(value / safeStep) * safeStep;
  return Math.min(MIN_CANDLES_SLIDER_MAX, Math.max(MIN_CANDLES_SLIDER_MIN, rounded));
}

/** Nominal bar length in minutes (MN ≈ 30 calendar days). */
export const TIMEFRAME_MINUTES: Record<Timeframe, number> = {
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
  D1: 1_440,
  W1: 10_080,
  MN: 43_200,
};

const DURATION_UNITS = [
  { minutes: 43_200, singular: "month", plural: "months" },
  { minutes: 10_080, singular: "week", plural: "weeks" },
  { minutes: 1_440, singular: "day", plural: "days" },
  { minutes: 60, singular: "hour", plural: "hours" },
  { minutes: 1, singular: "minute", plural: "minutes" },
] as const;

export function computeBuilderMinCandles(input: {
  signalType?: string;
  fastEma?: number;
  slowEma?: number;
  adxPeriod?: number;
  atrPeriod?: number;
  adxFilter?: boolean;
  atrFilter?: boolean;
  slStructureLookback?: number;
}): number {
  const periods: number[] = [];
  if (input.signalType === "monthly_high" || input.signalType === "monthly_low") {
    periods.push(31);
  }
  if (input.fastEma) periods.push(input.fastEma);
  if (input.slowEma) periods.push(input.slowEma);
  if (input.adxFilter && input.adxPeriod) periods.push(input.adxPeriod);
  if (input.atrFilter && input.atrPeriod) periods.push(input.atrPeriod);
  if (input.slStructureLookback) periods.push(input.slStructureLookback);

  const warmup = periods.length > 0 ? Math.max(...periods) : 50;
  return roundUpMinCandles(Math.min(MIN_CANDLES_SLIDER_MAX, warmup * 3));
}

/** Total calendar minutes covered by ``candles`` bars of ``timeframe``. */
export function candleLookbackMinutes(timeframe: Timeframe, candles: number): number {
  if (!Number.isFinite(candles) || candles <= 0) return 0;
  return TIMEFRAME_MINUTES[timeframe] * candles;
}

/** Format a minute span as a short human duration (e.g. "5 hours", "1 day"). */
export function formatDurationMinutes(totalMinutes: number): string {
  if (!Number.isFinite(totalMinutes) || totalMinutes <= 0) return "0 minutes";

  for (const unit of DURATION_UNITS) {
    if (totalMinutes < unit.minutes && unit.minutes !== 1) continue;
    const raw = totalMinutes / unit.minutes;
    const rounded = Number.isInteger(raw) ? raw : Math.round(raw * 10) / 10;
    if (rounded < 1 && unit.minutes !== 1) continue;
    const label = rounded === 1 ? unit.singular : unit.plural;
    const display = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
    return `${display} ${label}`;
  }

  return "0 minutes";
}

/** Human duration for a candle lookback (e.g. 50 × M15 → "12.5 hours"). */
export function formatCandleLookback(timeframe: Timeframe, candles: number): string {
  return formatDurationMinutes(candleLookbackMinutes(timeframe, candles));
}

export function defaultAdxFilter(): Extract<FilterSpec, { type: "adx" }> {
  return {
    id: "adx",
    type: "adx",
    enabled: true,
    period: 14,
    threshold: 25,
    compare: "gte",
  };
}

export function defaultAtrFilter(): Extract<FilterSpec, { type: "atr" }> {
  return {
    id: "atr",
    type: "atr",
    enabled: true,
    period: 14,
    min_value: 0.0008,
  };
}
