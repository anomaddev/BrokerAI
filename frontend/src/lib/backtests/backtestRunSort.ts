import type { BacktestRun } from "../../api/client";
import { TIMEFRAME_LABELS, type Timeframe } from "../strategyParams";
import { backtestRunStatusLabel, normalizeBacktestRunStatus } from "./backtestRunStatus";

export type BacktestRunSortKey =
  | "strategy"
  | "timeframe"
  | "assetClass"
  | "status"
  | "created"
  | "finished"
  | "trades"
  | "winRate"
  | "pnl";

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
  return [...runs].sort((a, b) => compareBacktestRuns(a, b, key, direction));
}
