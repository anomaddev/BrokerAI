import type { BacktestRun } from "../../api/client";
import { TIMEFRAME_LABELS, type Timeframe } from "../strategyParams";
import {
  backtestRunStatusLabel,
  backtestRunStatusPriority,
  normalizeBacktestRunStatus,
} from "./backtestRunStatus";

export type BacktestRunSortKey =
  | "name"
  | "strategy"
  | "timeframe"
  | "assetClass"
  | "status"
  | "created"
  | "finished"
  | "trades"
  | "winRate"
  | "pnl";

/** Display label for the Name column (run name, falling back to strategy). */
export function backtestRunNameLabel(run: BacktestRun): string {
  const name = (run.name || "").trim();
  if (name) return name;
  return (run.strategy_name || "").trim() || "—";
}

export type SortDirection = "asc" | "desc";

export function backtestRunTimeframeLabel(run: BacktestRun): string {
  const timeframe = run.timeframe;
  if (!timeframe) return "—";
  return TIMEFRAME_LABELS[timeframe as Timeframe] ?? timeframe;
}

function compareNullableNumber(a: number | null | undefined, b: number | null | undefined): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return a - b;
}

function compareNullableString(a: string | null | undefined, b: string | null | undefined): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  return a.localeCompare(b, undefined, { sensitivity: "base" });
}

export function compareBacktestRuns(
  a: BacktestRun,
  b: BacktestRun,
  key: BacktestRunSortKey,
  direction: SortDirection,
): number {
  let result = 0;
  switch (key) {
    case "name":
      result = backtestRunNameLabel(a).localeCompare(backtestRunNameLabel(b), undefined, {
        sensitivity: "base",
      });
      break;
    case "strategy":
      result = a.strategy_name.localeCompare(b.strategy_name, undefined, { sensitivity: "base" });
      break;
    case "timeframe":
      result = backtestRunTimeframeLabel(a).localeCompare(backtestRunTimeframeLabel(b), undefined, {
        sensitivity: "base",
      });
      break;
    case "assetClass":
      result = a.asset_class_label.localeCompare(b.asset_class_label, undefined, {
        sensitivity: "base",
      });
      break;
    case "status":
      result = backtestRunStatusLabel(normalizeBacktestRunStatus(a.status)).localeCompare(
        backtestRunStatusLabel(normalizeBacktestRunStatus(b.status)),
        undefined,
        { sensitivity: "base" },
      );
      break;
    case "created":
      result = compareNullableString(a.created_at, b.created_at);
      break;
    case "finished":
      result = compareNullableString(a.finished_at, b.finished_at);
      break;
    case "trades":
      result = compareNullableNumber(a.stats.total_trades, b.stats.total_trades);
      break;
    case "winRate":
      result = compareNullableNumber(a.stats.win_rate, b.stats.win_rate);
      break;
    case "pnl":
      result = compareNullableNumber(a.stats.realized_pnl, b.stats.realized_pnl);
      break;
    default:
      result = 0;
  }
  return direction === "asc" ? result : -result;
}

export function sortBacktestRuns(
  runs: BacktestRun[],
  key: BacktestRunSortKey,
  direction: SortDirection,
): BacktestRun[] {
  return [...runs].sort((a, b) => {
    const priority = backtestRunStatusPriority(a.status) - backtestRunStatusPriority(b.status);
    if (priority !== 0) return priority;
    return compareBacktestRuns(a, b, key, direction);
  });
}
