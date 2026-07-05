import type { StrategyAnalysisRun } from "../api/client";
import { TIMEFRAMES, type Timeframe } from "./strategyParams";

const DIRECTION_LABELS: Record<string, string> = {
  long: "Long",
  short: "Short",
};

const SIGNAL_LABELS: Record<string, string> = {
  bullish_cross: "Bullish cross",
  bearish_cross: "Bearish cross",
  none: "No signal",
};

const GATE_REASON_LABELS: Record<string, string> = {
  no_signal: "No signal",
  confidence_below_threshold: "Confidence below threshold",
  asset_session_inactive: "Asset session inactive",
  session_inactive: "Strategy session inactive",
  max_trades_reached: "Max trades reached",
};

export function directionLabel(direction: string | null | undefined): string {
  if (!direction) return "None";
  return DIRECTION_LABELS[direction] ?? direction;
}

export function directionClassName(direction: string | null | undefined): string {
  if (direction === "long") return "analysis-direction analysis-direction--long";
  if (direction === "short") return "analysis-direction analysis-direction--short";
  return "analysis-direction analysis-direction--none";
}

export function confidencePercent(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

export function signalLabel(run: StrategyAnalysisRun): string {
  const raw = run.metadata.signal;
  if (typeof raw === "string") {
    return SIGNAL_LABELS[raw] ?? raw.replace(/_/g, " ");
  }
  return run.signal_type.replace(/_/g, " ");
}

export function filterSummary(run: StrategyAnalysisRun): string {
  const filters = run.metadata.filters;
  if (!filters || typeof filters !== "object") return "—";
  const entries = Object.entries(filters as Record<string, unknown>);
  if (entries.length === 0) return "—";
  return entries
    .map(([id, detail]) => {
      if (!detail || typeof detail !== "object") return id;
      const passed = (detail as { passed?: boolean }).passed;
      return `${id}:${passed ? "pass" : "fail"}`;
    })
    .join(", ");
}

export function gateReasonLabel(reason: string): string {
  return GATE_REASON_LABELS[reason] ?? reason.replace(/_/g, " ");
}

export function isExecutorEligible(run: StrategyAnalysisRun): boolean {
  return run.confidence > 0 && run.direction != null;
}

export function executionOutcomeLabel(run: StrategyAnalysisRun): string {
  const execution = run.execution;
  if (!execution) {
    if (!isExecutorEligible(run)) return "—";
    return "Pending";
  }
  if (execution.intent_queued) return "Intent queued";
  if (!execution.gates_passed) {
    const reason = execution.gate_reasons[0];
    return reason ? `Gated: ${gateReasonLabel(reason)}` : "Gated";
  }
  if (!execution.priority_winner) return "Lower priority";
  if (run.direction == null) return "No signal";
  return "Passed gates";
}

export function executionOutcomeClassName(run: StrategyAnalysisRun): string {
  const execution = run.execution;
  if (!execution) {
    if (!isExecutorEligible(run)) return "analysis-outcome analysis-outcome--neutral";
    return "analysis-outcome analysis-outcome--pending";
  }
  if (execution.intent_queued) return "analysis-outcome analysis-outcome--intent";
  if (!execution.gates_passed || !execution.priority_winner) {
    return "analysis-outcome analysis-outcome--blocked";
  }
  if (run.direction == null) return "analysis-outcome analysis-outcome--neutral";
  return "analysis-outcome analysis-outcome--passed";
}

export type FilterDetail = {
  id: string;
  passed: boolean;
  values: Record<string, unknown>;
};

export function filterDetails(run: StrategyAnalysisRun): FilterDetail[] {
  const filters = run.metadata.filters;
  if (!filters || typeof filters !== "object") return [];
  return Object.entries(filters as Record<string, unknown>).map(([id, detail]) => {
    if (!detail || typeof detail !== "object") {
      return { id, passed: false, values: {} };
    }
    const record = detail as Record<string, unknown>;
    const { passed, ...values } = record;
    return {
      id,
      passed: Boolean(passed),
      values,
    };
  });
}

export function exploreHref(run: StrategyAnalysisRun): string {
  const params = new URLSearchParams({
    pair: run.pair,
    timeframe: run.timeframe,
  });
  return `/trading/explore?${params.toString()}`;
}

export type AnalysisSortColumn =
  | "time"
  | "strategy"
  | "pair"
  | "timeframe"
  | "direction"
  | "confidence"
  | "signal"
  | "filters"
  | "outcome";

export type AnalysisSortDirection = "asc" | "desc";

export const DEFAULT_ANALYSIS_SORT_COLUMN: AnalysisSortColumn = "time";
export const DEFAULT_ANALYSIS_SORT_DIRECTION: AnalysisSortDirection = "desc";

/** Default direction when a column header is first activated. */
export function defaultAnalysisSortDirection(column: AnalysisSortColumn): AnalysisSortDirection {
  if (column === "time" || column === "confidence") {
    return "desc";
  }
  return "asc";
}

function compareNullableStrings(a: string | null | undefined, b: string | null | undefined): number {
  const aText = a?.trim() ?? "";
  const bText = b?.trim() ?? "";
  if (!aText && !bText) return 0;
  if (!aText) return 1;
  if (!bText) return -1;
  return aText.localeCompare(bText);
}

function directionSortKey(direction: string | null | undefined): number {
  if (direction === "long") return 0;
  if (direction === "short") return 1;
  return 2;
}

function timeframeSortKey(timeframe: string): number {
  const index = TIMEFRAMES.indexOf(timeframe as Timeframe);
  return index >= 0 ? index : TIMEFRAMES.length;
}

/** Stable ordering for execution outcome labels (pending → blocked → passed). */
export function executionOutcomeSortKey(run: StrategyAnalysisRun): number {
  const execution = run.execution;
  if (!execution) return 0;
  if (execution.intent_queued) return 5;
  if (!execution.gates_passed) return 1;
  if (!execution.priority_winner) return 2;
  if (run.direction == null) return 3;
  return 4;
}

function compareAnalysisRunsByColumn(
  a: StrategyAnalysisRun,
  b: StrategyAnalysisRun,
  column: AnalysisSortColumn,
): number {
  switch (column) {
    case "time": {
      const aMs = Date.parse(a.analyzed_at);
      const bMs = Date.parse(b.analyzed_at);
      const aValid = Number.isFinite(aMs);
      const bValid = Number.isFinite(bMs);
      if (!aValid && !bValid) return 0;
      if (!aValid) return 1;
      if (!bValid) return -1;
      return aMs - bMs;
    }
    case "strategy":
      return compareNullableStrings(a.strategy_name, b.strategy_name);
    case "pair":
      return compareNullableStrings(a.pair, b.pair);
    case "timeframe":
      return timeframeSortKey(a.timeframe) - timeframeSortKey(b.timeframe);
    case "direction":
      return directionSortKey(a.direction) - directionSortKey(b.direction);
    case "confidence":
      return a.confidence - b.confidence;
    case "signal":
      return compareNullableStrings(signalLabel(a), signalLabel(b));
    case "filters":
      return compareNullableStrings(filterSummary(a), filterSummary(b));
    case "outcome": {
      const byKey = executionOutcomeSortKey(a) - executionOutcomeSortKey(b);
      if (byKey !== 0) return byKey;
      return compareNullableStrings(executionOutcomeLabel(a), executionOutcomeLabel(b));
    }
    default:
      return 0;
  }
}

export function sortAnalysisRunsForTable(
  runs: StrategyAnalysisRun[],
  options: {
    sortColumn: AnalysisSortColumn;
    sortDirection: AnalysisSortDirection;
  },
): StrategyAnalysisRun[] {
  const { sortColumn, sortDirection } = options;
  const directionMultiplier = sortDirection === "asc" ? 1 : -1;
  return [...runs].sort(
    (a, b) => directionMultiplier * compareAnalysisRunsByColumn(a, b, sortColumn),
  );
}
