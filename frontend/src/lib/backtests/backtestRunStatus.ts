import type { BacktestRunStatus } from "../../api/client";

const BACKTEST_RUN_STATUS_LABELS: Record<BacktestRunStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

/** Running first, then queued, then terminal — used for the top-of-table ordering. */
const STATUS_PRIORITY: Record<BacktestRunStatus, number> = {
  running: 0,
  queued: 1,
  completed: 2,
  failed: 3,
  cancelled: 4,
};

export function normalizeBacktestRunStatus(
  status: BacktestRunStatus | string | undefined | null,
): BacktestRunStatus {
  if (
    status === "queued" ||
    status === "running" ||
    status === "completed" ||
    status === "failed" ||
    status === "cancelled"
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

export function backtestRunStatusPriority(
  status: BacktestRunStatus | string | undefined | null,
): number {
  return STATUS_PRIORITY[normalizeBacktestRunStatus(status)];
}
