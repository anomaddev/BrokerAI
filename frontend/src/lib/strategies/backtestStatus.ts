import type { BacktestStatus } from "../../api/client";

const BACKTEST_STATUS_LABELS: Record<BacktestStatus, string> = {
  not_run: "Not run",
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

export function normalizeBacktestStatus(status: BacktestStatus | undefined | null): BacktestStatus {
  if (
    status === "queued" ||
    status === "running" ||
    status === "completed" ||
    status === "failed"
  ) {
    return status;
  }
  return "not_run";
}

export function backtestStatusLabel(status: BacktestStatus | undefined | null): string {
  return BACKTEST_STATUS_LABELS[normalizeBacktestStatus(status)];
}
