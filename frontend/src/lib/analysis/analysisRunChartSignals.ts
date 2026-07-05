import type { StrategyAnalysisRun } from "../../api/client";
import type { CrossoverSignal } from "../chart/indicators";
import { parseAppInstant } from "../formatTime";

function crossoverTypeFromRun(
  run: StrategyAnalysisRun,
): CrossoverSignal["type"] | null {
  const raw = run.metadata.signal;
  if (raw === "bullish_cross") return "bullish";
  if (raw === "bearish_cross") return "bearish";
  if (run.direction === "long") return "bullish";
  if (run.direction === "short") return "bearish";
  return null;
}

/**
 * Build the crossover flag recorded by the live analyzer for this run.
 *
 * Chart recomputation can diverge when warmup history differs from the bot cache;
 * pinning ``metadata.crossover_time`` keeps the UI aligned with the stored analysis.
 */
export function analysisRunCrossoverSignal(
  run: StrategyAnalysisRun,
): CrossoverSignal | null {
  const type = crossoverTypeFromRun(run);
  if (!type) return null;

  const rawTime = run.metadata.crossover_time ?? run.candle_time;
  if (rawTime == null) return null;

  const date = parseAppInstant(String(rawTime));
  if (!date) return null;

  const adx =
    typeof run.metadata.adx === "number" && Number.isFinite(run.metadata.adx)
      ? run.metadata.adx
      : 20;
  const confidence =
    run.confidence > 0 && run.confidence <= 1
      ? Math.round(run.confidence * 100)
      : Math.round(run.confidence);

  return {
    time: Math.floor(date.getTime() / 1000),
    type,
    price: 0,
    confidence,
    adx,
  };
}

export function mergeCrossoverSignals(
  computed: CrossoverSignal[],
  pinned: CrossoverSignal[],
): CrossoverSignal[] {
  if (pinned.length === 0) return computed;
  const merged = [...computed];
  for (const signal of pinned) {
    const exists = merged.some(
      (entry) => entry.time === signal.time && entry.type === signal.type,
    );
    if (!exists) merged.push(signal);
  }
  return merged;
}

export type SignalLookback = {
  /** Unix seconds for the analyzed candle (signals must fall on bars ending here). */
  anchorTime: number;
  bars?: number;
};

function resolveAnchorCandleIndex(sortedTimes: number[], anchorTime: number): number {
  const exact = sortedTimes.indexOf(anchorTime);
  if (exact !== -1) return exact;

  let idx = -1;
  for (let i = 0; i < sortedTimes.length; i += 1) {
    if (sortedTimes[i] <= anchorTime) idx = i;
    else break;
  }
  if (idx !== -1) return idx;
  return sortedTimes.length - 1;
}

/** Keep crossover flags that occur on one of the last ``bars`` candles ending at ``anchorTime``. */
export function filterSignalsWithinLastNCandles(
  signals: CrossoverSignal[],
  candleTimes: number[],
  anchorTime: number,
  bars = 10,
): CrossoverSignal[] {
  if (signals.length === 0 || candleTimes.length === 0) return signals;

  const sorted = [...new Set(candleTimes)].sort((left, right) => left - right);
  const anchorIdx = resolveAnchorCandleIndex(sorted, anchorTime);
  const lookback = Math.max(1, bars);
  const startIdx = Math.max(0, anchorIdx - lookback + 1);
  const allowed = new Set(sorted.slice(startIdx, anchorIdx + 1));

  return signals.filter((signal) => allowed.has(signal.time));
}

export function applySignalLookback(
  signals: CrossoverSignal[],
  candleTimes: number[],
  lookback: SignalLookback | null | undefined,
): CrossoverSignal[] {
  if (!lookback) return signals;
  return filterSignalsWithinLastNCandles(
    signals,
    candleTimes,
    lookback.anchorTime,
    lookback.bars ?? 10,
  );
}
