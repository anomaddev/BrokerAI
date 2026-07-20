import type { StrategyAnalysisRun } from "../api/client";
import { TIMEFRAMES, type Timeframe } from "./strategyParams";

const DIRECTION_LABELS: Record<string, string> = {
  long: "Long",
  short: "Short",
};

const SIGNAL_LABELS: Record<string, string> = {
  bullish_cross: "Bullish Cross",
  bearish_cross: "Bearish Cross",
  approaching_bullish_cross: "Approaching Bullish",
  approaching_bearish_cross: "Approaching Bearish",
  approaching: "Approaching",
  approaching_cross: "Approaching",
  none: "No signal",
};

export type AnalysisDirectionFilterValue = "long" | "short" | "none";

export const ANALYSIS_DIRECTION_FILTER_OPTIONS: {
  value: AnalysisDirectionFilterValue;
  label: string;
}[] = [
  { value: "long", label: "Long" },
  { value: "short", label: "Short" },
  { value: "none", label: "None" },
];

export const DEFAULT_ANALYSIS_DIRECTION_FILTERS = new Set<AnalysisDirectionFilterValue>([
  "long",
  "short",
  "none",
]);

export function analysisRunDirectionCategory(
  run: Pick<StrategyAnalysisRun, "direction">,
): AnalysisDirectionFilterValue {
  if (run.direction === "long") return "long";
  if (run.direction === "short") return "short";
  return "none";
}

const GATE_REASON_LABELS: Record<string, string> = {
  no_signal: "No signal",
  confidence_below_threshold: "Confidence below threshold",
  asset_session_inactive: "Asset session inactive",
  session_inactive: "Session inactive (requires global and strategy)",
  asset_disabled: "Asset class disabled globally",
  pair_not_enabled: "Pair not enabled globally",
  late_market_trading: "Late market trading blocked",
  max_trades_reached: "Max trades reached",
  filters_failed: "Filters failed",
  open_position_exists: "Open position on pair",
  no_exit_signal: "No exit signal",
};

const FILTER_GATE_PREFIX = "filter_";
const FILTER_GATE_SUFFIX = "_failed";

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

/** Human label for how an analysis run was created (`run_type` from the API). */
export function runSourceLabel(run: StrategyAnalysisRun): string {
  if (isExitAnalysisRun(run)) return "Exit";
  return run.run_type === "manual" ? "User" : "Bot";
}

export function runSourceClassName(run: StrategyAnalysisRun): string {
  if (isExitAnalysisRun(run)) {
    return "analysis-source analysis-source--exit";
  }
  return run.run_type === "manual"
    ? "analysis-source analysis-source--user"
    : "analysis-source analysis-source--bot";
}

export function isExitAnalysisRun(run: StrategyAnalysisRun): boolean {
  return run.analysis_purpose === "exit" || run.execution?.analysis_purpose === "exit";
}

export function analysisPurposeLabel(run: StrategyAnalysisRun): string {
  return isExitAnalysisRun(run) ? "Exit" : "Entry";
}

export function analysisPurposeClassName(run: StrategyAnalysisRun): string {
  return isExitAnalysisRun(run)
    ? "analysis-purpose analysis-purpose--exit"
    : "analysis-purpose analysis-purpose--entry";
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

export function gateReasonLabel(
  reason: string,
  details?: Record<string, Record<string, unknown>>,
): string {
  if (reason.startsWith(FILTER_GATE_PREFIX) && reason.endsWith(FILTER_GATE_SUFFIX)) {
    const filterId = reason.slice(
      FILTER_GATE_PREFIX.length,
      reason.length - FILTER_GATE_SUFFIX.length,
    );
    const label = formatFilterGateLabel(filterId);
    const metrics = details?.[reason];
    if (metrics) {
      return `${label} failed (${formatGateMetrics(metrics)})`;
    }
    return `${label} failed`;
  }
  return GATE_REASON_LABELS[reason] ?? reason.replace(/_/g, " ");
}

function formatFilterGateLabel(filterId: string): string {
  const labels: Record<string, string> = {
    adx: "ADX filter",
    atr: "ATR filter",
    rsi: "RSI filter",
  };
  return labels[filterId.toLowerCase()] ?? `${filterId} filter`;
}

function formatGateMetrics(metrics: Record<string, unknown>): string {
  const parts: string[] = [];
  if (metrics.adx != null && metrics.threshold != null) {
    parts.push(`ADX ${formatMetricNumber(metrics.adx)} < ${formatMetricNumber(metrics.threshold)}`);
  } else if (metrics.atr != null && metrics.min_value != null) {
    parts.push(`ATR ${formatMetricNumber(metrics.atr)} < min ${formatMetricNumber(metrics.min_value)}`);
  } else if (metrics.confidence_pct != null && metrics.min_confidence_pct != null) {
    parts.push(
      `${formatMetricNumber(metrics.confidence_pct)}% < ${formatMetricNumber(metrics.min_confidence_pct)}%`,
    );
  } else if (metrics.count != null && metrics.max_trades_per_day != null) {
    parts.push(`${metrics.count} / ${metrics.max_trades_per_day} trades today`);
  } else {
    for (const [key, value] of Object.entries(metrics)) {
      if (key === "evaluated_at" || key === "compare") continue;
      parts.push(`${key.replace(/_/g, " ")}: ${formatMetricNumber(value)}`);
    }
  }
  return parts.join(", ") || "see metrics";
}

function formatMetricNumber(value: unknown): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  return String(value);
}

export function isActionableSignal(signal: unknown): boolean {
  if (typeof signal !== "string" || !signal.trim()) return false;
  const normalized = signal.trim().toLowerCase();
  if (normalized === "none") return false;
  if (normalized.includes("approach")) return false;
  return true;
}

export function isApproachingSignal(run: Pick<StrategyAnalysisRun, "metadata">): boolean {
  const raw = run.metadata.signal;
  return typeof raw === "string" && raw.toLowerCase().includes("approach");
}

export function isExecutorEligible(run: StrategyAnalysisRun): boolean {
  if (!isActionableSignal(run.metadata.signal)) return false;
  return run.confidence > 0 && run.direction != null;
}

export function executionOutcomeLabel(run: StrategyAnalysisRun): string {
  const execution = run.execution;
  if (isExitAnalysisRun(run)) {
    if (!execution) return "Pending";
    if (execution.exit_closed) return "Exit closed";
    if (execution.exit_triggered) return "Exit triggered";
    const reason = execution.gate_reasons[0];
    return reason ? gateReasonLabel(reason, execution.gate_details) : "No exit";
  }
  if (!execution) {
    if (!isExecutorEligible(run)) return "—";
    return "Pending";
  }
  if (execution.intent_queued) return "Intent queued";
  if (!execution.gates_passed) {
    const reason = execution.gate_reasons[0];
    return reason
      ? `Gated: ${gateReasonLabel(reason, execution.gate_details)}`
      : "Gated";
  }
  if (!execution.priority_winner) return "Lower priority";
  if (run.direction == null) return "No signal";
  return "Passed gates";
}

export function executionOutcomeClassName(run: StrategyAnalysisRun): string {
  const execution = run.execution;
  if (isExitAnalysisRun(run)) {
    if (!execution) return "analysis-outcome analysis-outcome--pending";
    if (execution.exit_closed) return "analysis-outcome analysis-outcome--exit-closed";
    if (execution.exit_triggered) return "analysis-outcome analysis-outcome--exit-triggered";
    return "analysis-outcome analysis-outcome--neutral";
  }
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

const HIDDEN_FILTER_METRIC_KEYS = new Set(["evaluated_at"]);

function visibleFilterMetricValues(
  filterId: string,
  values: Record<string, unknown>,
): Record<string, unknown> {
  const normalized = filterId.trim().toLowerCase();
  if (normalized !== "adx" && normalized !== "atr") {
    return values;
  }
  return Object.fromEntries(
    Object.entries(values).filter(([key]) => !HIDDEN_FILTER_METRIC_KEYS.has(key)),
  );
}

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
      values: visibleFilterMetricValues(id, values),
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
  | "source"
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

function runSourceSortKey(run: StrategyAnalysisRun): number {
  if (isExitAnalysisRun(run)) return 2;
  return run.run_type === "manual" ? 0 : 1;
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
    case "source":
      return runSourceSortKey(a) - runSourceSortKey(b);
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

/** One-line summary for grouped analysis pair rows. */
export function analysisRunBriefSummary(run: StrategyAnalysisRun): string {
  const parts: string[] = [];
  parts.push(directionLabel(run.direction));
  if (run.confidence > 0) {
    parts.push(confidencePercent(run.confidence));
  }
  parts.push(signalLabel(run));
  const outcome = executionOutcomeLabel(run);
  if (outcome && outcome !== "—") {
    parts.push(outcome);
  }
  return parts.join(" · ");
}
