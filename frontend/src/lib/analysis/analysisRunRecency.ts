import type { StrategyAnalysisRun } from "../api/client";
import {
  analysisCandleOpenTime,
  analysisChartTimeframe,
} from "./analysisCandleWindow";
import { barOpenTimesMatch, expectedLatestClosedBar } from "../marketCalendar";
import { parseAppInstant } from "../formatTime";

function candleOpenMs(
  run: Pick<StrategyAnalysisRun, "candle_time" | "analyzed_at" | "metadata" | "timeframe">,
): number {
  const openIso = analysisCandleOpenTime(run);
  if (!openIso) return Number.NEGATIVE_INFINITY;
  const parsed = parseAppInstant(openIso);
  return parsed?.getTime() ?? Number.NEGATIVE_INFINITY;
}

/** True when this run analyzed the market's latest fully closed bar. */
export function isCurrentBarAnalysis(
  run: Pick<StrategyAnalysisRun, "candle_time" | "analyzed_at" | "metadata" | "timeframe">,
  asOfMs: number = Date.now(),
): boolean {
  const openIso = analysisCandleOpenTime(run);
  const timeframe = analysisChartTimeframe(run.timeframe);
  const expected = expectedLatestClosedBar(timeframe, new Date(asOfMs));
  return barOpenTimesMatch(openIso, expected);
}

/**
 * Newest stored run per strategy/pair/timeframe that is behind the latest closed bar.
 *
 * Used to surface "bot has not analyzed the current bar yet" without flagging older history.
 */
export function buildStaleAnalysisRunIds(
  runs: StrategyAnalysisRun[],
  asOfMs: number = Date.now(),
): Set<string> {
  const latestByKey = new Map<string, StrategyAnalysisRun>();

  for (const run of runs) {
    const key = `${run.strategy_id}|${run.pair}|${run.timeframe}`;
    const existing = latestByKey.get(key);
    if (!existing || candleOpenMs(run) > candleOpenMs(existing)) {
      latestByKey.set(key, run);
    }
  }

  const stale = new Set<string>();
  for (const run of latestByKey.values()) {
    if (!isCurrentBarAnalysis(run, asOfMs)) {
      stale.add(run.id);
    }
  }

  return stale;
}

export type AnalysisRunRecency = "current" | "stale" | "historical";

export function analysisRunRecency(
  run: StrategyAnalysisRun,
  staleRunIds: Set<string>,
  asOfMs: number = Date.now(),
): AnalysisRunRecency {
  if (isCurrentBarAnalysis(run, asOfMs)) return "current";
  if (staleRunIds.has(run.id)) return "stale";
  return "historical";
}
