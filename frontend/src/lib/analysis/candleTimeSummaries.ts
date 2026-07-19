import type { Strategy, StrategyAnalysisRun } from "../../api/client";
import { TIMEFRAMES } from "../strategyParams";
import { runSourceLabel } from "../strategyAnalysis";
import { formatCandleGroupLabel } from "./analysisRunGrouping";
import { analysisRunRecency, buildStaleAnalysisRunIds } from "./analysisRunRecency";
import { buildExitAnalysisRows } from "./exitAnalysis";
import type { Trade } from "../../api/client";

export type CandleTimeSummary = {
  key: string;
  label: string;
  sources: string[];
  timeframes: string[];
  assetClasses: string[];
  strategyCount: number;
  runCount: number;
  exitMonitorTradeCount: number;
  isCurrentBar: boolean;
};

const TIMEFRAME_ORDER = new Map(TIMEFRAMES.map((value, index) => [value, index]));

const SOURCE_ORDER: Record<string, number> = {
  Bot: 0,
  User: 1,
  Exit: 2,
};

function compareTimeframes(a: string, b: string): number {
  const aIndex = TIMEFRAME_ORDER.get(a as (typeof TIMEFRAMES)[number]) ?? 999;
  const bIndex = TIMEFRAME_ORDER.get(b as (typeof TIMEFRAMES)[number]) ?? 999;
  if (aIndex !== bIndex) return aIndex - bIndex;
  return a.localeCompare(b);
}

function compareSources(a: string, b: string): number {
  const aIndex = SOURCE_ORDER[a] ?? 99;
  const bIndex = SOURCE_ORDER[b] ?? 99;
  if (aIndex !== bIndex) return aIndex - bIndex;
  return a.localeCompare(b);
}

export function compareCandleKeys(a: string, b: string): number {
  if (a === "unknown") return 1;
  if (b === "unknown") return -1;
  return b.localeCompare(a);
}

function candleKeyForRun(run: StrategyAnalysisRun): string {
  return run.candle_time ?? "unknown";
}

function assetClassLabel(
  run: StrategyAnalysisRun,
  strategiesById: Map<string, Strategy>,
): string {
  return strategiesById.get(run.strategy_id)?.asset_class_label ?? "—";
}

function buildExitCountByCandleKey(
  openTrades: Trade[],
  exitRuns: StrategyAnalysisRun[],
): Map<string, number> {
  const counts = new Map<string, number>();
  const rows = buildExitAnalysisRows(openTrades, exitRuns);

  for (const row of rows) {
    if (!row.latestRun) continue;
    const key = candleKeyForRun(row.latestRun);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  return counts;
}

/** Aggregate entry + exit runs into one row per candle time (newest first). */
export function buildCandleTimeSummaries(
  runs: StrategyAnalysisRun[],
  strategiesById: Map<string, Strategy>,
  formatInstant: (iso: string, style?: "compact" | "short") => string,
  options?: {
    openTrades?: Trade[];
    exitRuns?: StrategyAnalysisRun[];
    asOfMs?: number;
  },
): CandleTimeSummary[] {
  const byCandle = new Map<string, StrategyAnalysisRun[]>();

  for (const run of runs) {
    const key = candleKeyForRun(run);
    const list = byCandle.get(key) ?? [];
    list.push(run);
    byCandle.set(key, list);
  }

  const staleRunIds = buildStaleAnalysisRunIds(runs, options?.asOfMs);
  const exitCountByKey = buildExitCountByCandleKey(
    options?.openTrades ?? [],
    options?.exitRuns ?? [],
  );

  const candleKeys = [...byCandle.keys()].sort(compareCandleKeys);

  return candleKeys.map((key) => {
    const candleRuns = byCandle.get(key) ?? [];

    const sources = [...new Set(candleRuns.map((run) => runSourceLabel(run)))].sort(
      compareSources,
    );
    const timeframes = [...new Set(candleRuns.map((run) => run.timeframe))].sort(
      compareTimeframes,
    );
    const assetClasses = [
      ...new Set(candleRuns.map((run) => assetClassLabel(run, strategiesById))),
    ].sort((a, b) => a.localeCompare(b));
    const strategyIds = new Set(candleRuns.map((run) => run.strategy_id));

    const isCurrentBar = candleRuns.some(
      (run) => analysisRunRecency(run, staleRunIds, options?.asOfMs) === "current",
    );

    return {
      key,
      label: formatCandleGroupLabel(key === "unknown" ? null : key, formatInstant),
      sources,
      timeframes,
      assetClasses,
      strategyCount: strategyIds.size,
      runCount: candleRuns.length,
      exitMonitorTradeCount: exitCountByKey.get(key) ?? 0,
      isCurrentBar,
    };
  });
}

/** Runs belonging to a single candle key. */
export function runsForCandleKey(
  runs: StrategyAnalysisRun[],
  candleKey: string,
): StrategyAnalysisRun[] {
  return runs.filter((run) => candleKeyForRun(run) === candleKey);
}
