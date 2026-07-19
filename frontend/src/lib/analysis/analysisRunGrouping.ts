import type { Strategy, StrategyAnalysisRun } from "../../api/client";
import { TIMEFRAMES } from "../strategyParams";
import { runSourceLabel } from "../strategyAnalysis";

export type AnalysisRunGroupLevel =
  | "candle"
  | "asset_class"
  | "strategy"
  | "timeframe"
  | "source"
  | "pairs";

export type AnalysisRunGroupNode = {
  key: string;
  label: string;
  level: AnalysisRunGroupLevel;
  count: number;
  children: AnalysisRunGroupNode[];
  runs: StrategyAnalysisRun[];
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

function compareCandleKeys(a: string, b: string): number {
  if (a === "unknown") return 1;
  if (b === "unknown") return -1;
  return b.localeCompare(a);
}

function groupRuns<T>(
  runs: StrategyAnalysisRun[],
  keyFn: (run: StrategyAnalysisRun) => T,
): Map<T, StrategyAnalysisRun[]> {
  const groups = new Map<T, StrategyAnalysisRun[]>();
  for (const run of runs) {
    const key = keyFn(run);
    const list = groups.get(key) ?? [];
    list.push(run);
    groups.set(key, list);
  }
  return groups;
}

function countRuns(node: AnalysisRunGroupNode): number {
  if (node.runs.length > 0) {
    return node.runs.length;
  }
  return node.children.reduce((total, child) => total + child.count, 0);
}

function buildSourceGroups(runs: StrategyAnalysisRun[]): AnalysisRunGroupNode[] {
  const bySource = groupRuns(runs, (run) => runSourceLabel(run));
  const sourceKeys = [...bySource.keys()].sort(compareSources);

  return sourceKeys.map((source) => {
    const sourceRuns = [...(bySource.get(source) ?? [])].sort((a, b) =>
      a.pair.localeCompare(b.pair),
    );
    return {
      key: source,
      label: source,
      level: "pairs" as const,
      count: sourceRuns.length,
      children: [],
      runs: sourceRuns,
    };
  });
}

function buildTimeframeGroups(runs: StrategyAnalysisRun[]): AnalysisRunGroupNode[] {
  const byTimeframe = groupRuns(runs, (run) => run.timeframe);
  const timeframeKeys = [...byTimeframe.keys()].sort(compareTimeframes);

  return timeframeKeys.map((timeframe) => {
    const children = buildSourceGroups(byTimeframe.get(timeframe) ?? []);
    const node: AnalysisRunGroupNode = {
      key: timeframe,
      label: timeframe,
      level: "timeframe",
      count: 0,
      children,
      runs: [],
    };
    node.count = countRuns(node);
    return node;
  });
}

function buildStrategyGroups(
  runs: StrategyAnalysisRun[],
): AnalysisRunGroupNode[] {
  const byStrategy = groupRuns(runs, (run) => run.strategy_name);
  const strategyKeys = [...byStrategy.keys()].sort((a, b) => a.localeCompare(b));

  return strategyKeys.map((strategyName) => {
    const children = buildTimeframeGroups(byStrategy.get(strategyName) ?? []);
    const node: AnalysisRunGroupNode = {
      key: strategyName,
      label: strategyName,
      level: "strategy",
      count: 0,
      children,
      runs: [],
    };
    node.count = countRuns(node);
    return node;
  });
}

function buildAssetClassGroups(
  runs: StrategyAnalysisRun[],
  strategiesById: Map<string, Strategy>,
): AnalysisRunGroupNode[] {
  const byAsset = groupRuns(runs, (run) => {
    const strategy = strategiesById.get(run.strategy_id);
    return strategy?.asset_class ?? "unknown";
  });

  const assetKeys = [...byAsset.keys()].sort((a, b) => {
    const aLabel =
      strategiesById.get(
        byAsset.get(a)?.[0]?.strategy_id ?? "",
      )?.asset_class_label ?? a;
    const bLabel =
      strategiesById.get(
        byAsset.get(b)?.[0]?.strategy_id ?? "",
      )?.asset_class_label ?? b;
    return aLabel.localeCompare(bLabel);
  });

  return assetKeys.map((assetClass) => {
    const assetRuns = byAsset.get(assetClass) ?? [];
    const label =
      strategiesById.get(assetRuns[0]?.strategy_id ?? "")?.asset_class_label ??
      assetClass;
    const children = buildStrategyGroups(assetRuns);
    const node: AnalysisRunGroupNode = {
      key: assetClass,
      label,
      level: "asset_class",
      count: 0,
      children,
      runs: [],
    };
    node.count = countRuns(node);
    return node;
  });
}

export function formatCandleGroupLabel(
  candleTime: string | null,
  formatInstant: (iso: string, style?: "compact" | "short") => string,
): string {
  if (!candleTime || candleTime === "unknown") {
    return "Unknown candle";
  }
  return formatInstant(candleTime, "compact");
}

/** Build nested analysis groups: candle → asset → strategy → timeframe → source → pairs. */
export function buildAnalysisRunGroups(
  runs: StrategyAnalysisRun[],
  strategiesById: Map<string, Strategy>,
  formatInstant: (iso: string, style?: "compact" | "short") => string,
): AnalysisRunGroupNode[] {
  const byCandle = groupRuns(runs, (run) => run.candle_time ?? "unknown");
  const candleKeys = [...byCandle.keys()].sort(compareCandleKeys);

  return candleKeys.map((candleKey) => {
    const candleRuns = byCandle.get(candleKey) ?? [];
    const children = buildAssetClassGroups(candleRuns, strategiesById);
    const node: AnalysisRunGroupNode = {
      key: candleKey,
      label: formatCandleGroupLabel(candleKey === "unknown" ? null : candleKey, formatInstant),
      level: "candle",
      count: 0,
      children,
      runs: [],
    };
    node.count = countRuns(node);
    return node;
  });
}

/** Flatten all runs from a group tree (pre-order). */
export function flattenAnalysisRunGroups(
  groups: AnalysisRunGroupNode[],
): StrategyAnalysisRun[] {
  const flattened: StrategyAnalysisRun[] = [];

  function walk(node: AnalysisRunGroupNode) {
    if (node.runs.length > 0) {
      flattened.push(...node.runs);
      return;
    }
    for (const child of node.children) {
      walk(child);
    }
  }

  for (const group of groups) {
    walk(group);
  }

  return flattened;
}

/** Collect default expanded keys for the newest candle batch. */
export function defaultExpandedGroupKeys(
  groups: AnalysisRunGroupNode[],
): Set<string> {
  const expanded = new Set<string>();
  const latestCandle = groups[0];
  if (!latestCandle) {
    return expanded;
  }

  expanded.add(`${latestCandle.level}:${latestCandle.key}`);

  for (const assetGroup of latestCandle.children) {
    expanded.add(`${assetGroup.level}:${assetGroup.key}`);
    for (const strategyGroup of assetGroup.children) {
      expanded.add(`${strategyGroup.level}:${strategyGroup.key}`);
    }
  }

  return expanded;
}

export function groupNodeId(node: Pick<AnalysisRunGroupNode, "level" | "key">): string {
  return `${node.level}:${node.key}`;
}

export type CandleBatch = {
  key: string;
  label: string;
  runs: StrategyAnalysisRun[];
  count: number;
};

/** Group runs into candle-time batches (newest first). */
export function buildCandleBatches(
  runs: StrategyAnalysisRun[],
  formatInstant: (iso: string, style?: "compact" | "short") => string,
): CandleBatch[] {
  const byCandle = groupRuns(runs, (run) => run.candle_time ?? "unknown");
  const candleKeys = [...byCandle.keys()].sort(compareCandleKeys);

  return candleKeys.map((candleKey) => {
    const batchRuns = byCandle.get(candleKey) ?? [];
    return {
      key: candleKey,
      label: formatCandleGroupLabel(
        candleKey === "unknown" ? null : candleKey,
        formatInstant,
      ),
      runs: batchRuns,
      count: batchRuns.length,
    };
  });
}

function assetClassLabel(
  run: StrategyAnalysisRun,
  strategiesById: Map<string, Strategy>,
): string {
  return strategiesById.get(run.strategy_id)?.asset_class_label ?? "—";
}

/** Stable table order within a candle batch. */
export function sortRunsForEntryTable(
  runs: StrategyAnalysisRun[],
  strategiesById: Map<string, Strategy>,
): StrategyAnalysisRun[] {
  return [...runs].sort((a, b) => {
    const assetCompare = assetClassLabel(a, strategiesById).localeCompare(
      assetClassLabel(b, strategiesById),
    );
    if (assetCompare !== 0) return assetCompare;

    const strategyCompare = a.strategy_name.localeCompare(b.strategy_name);
    if (strategyCompare !== 0) return strategyCompare;

    const timeframeCompare = compareTimeframes(a.timeframe, b.timeframe);
    if (timeframeCompare !== 0) return timeframeCompare;

    const sourceCompare = compareSources(runSourceLabel(a), runSourceLabel(b));
    if (sourceCompare !== 0) return sourceCompare;

    return a.pair.localeCompare(b.pair);
  });
}

/** Breadcrumb label for a visual group divider row in the entry table. */
export function entryTableGroupLabel(
  run: StrategyAnalysisRun,
  strategiesById: Map<string, Strategy>,
): string {
  return [
    assetClassLabel(run, strategiesById),
    run.strategy_name,
    run.timeframe,
    runSourceLabel(run),
  ].join(" · ");
}
