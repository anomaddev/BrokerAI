import type { CandleTimeSummary } from "./candleTimeSummaries";

/** Passed via router state when opening a candle from the summary table. */
export type CandleNavigationState = {
  candleKeys: string[];
};

export function buildCandleNavKeys(summaries: CandleTimeSummary[]): string[] {
  return summaries.map((summary) => summary.key);
}

export function resolveCandleNeighbors(
  candleKeys: string[],
  candleKey: string,
): {
  previousKey: string | null;
  nextKey: string | null;
  index: number;
  total: number;
} {
  const index = candleKeys.indexOf(candleKey);
  if (index < 0) {
    return { previousKey: null, nextKey: null, index: -1, total: candleKeys.length };
  }
  return {
    previousKey: index > 0 ? candleKeys[index - 1]! : null,
    nextKey: index < candleKeys.length - 1 ? candleKeys[index + 1]! : null,
    index,
    total: candleKeys.length,
  };
}

/** Prefer the newest candle that analyzed the current bar; else newest candle overall. */
export function resolveCurrentCandleKey(
  summaries: CandleTimeSummary[],
): string | null {
  const current = summaries.find((summary) => summary.isCurrentBar);
  if (current) {
    return current.key;
  }
  return summaries[0]?.key ?? null;
}
