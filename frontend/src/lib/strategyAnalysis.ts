import type { StrategyAnalysisRun } from "../api/client";

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

export function executionOutcomeLabel(run: StrategyAnalysisRun): string {
  const execution = run.execution;
  if (!execution) return "Pending";
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
  if (!execution) return "analysis-outcome analysis-outcome--pending";
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
