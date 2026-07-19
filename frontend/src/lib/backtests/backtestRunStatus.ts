import type { BacktestRunStatus } from "../../api/client";

const BACKTEST_RUN_STATUS_LABELS: Record<BacktestRunStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

export function normalizeBacktestRunStatus(
  status: BacktestRunStatus | string | undefined | null,
): BacktestRunStatus {
  if (
    status === "queued" ||
    status === "running" ||
    status === "completed" ||
    status === "failed"
  ) {
    return status;
  }
  return "queued";
}

export function backtestRunStatusLabel(
  status: BacktestRunStatus | string | undefined | null,
): string {
  return BACKTEST_RUN_STATUS_LABELS[normalizeBacktestRunStatus(status)];
}
