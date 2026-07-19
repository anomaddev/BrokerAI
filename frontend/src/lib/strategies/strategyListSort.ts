import type { Strategy } from "../../api/client";
import { TIMEFRAME_LABELS, type Timeframe } from "../strategyParams";
import { backtestStatusLabel, normalizeBacktestStatus } from "./backtestStatus";

export type StrategySortKey =
  | "name"
  | "timeframe"
  | "type"
  | "assetClass"
  | "status"
  | "backtest"
  | "trades"
  | "winRate"
  | "pnl"
  | "open"
  | "lastTrade";

export type SortDirection = "asc" | "desc";

export function strategyTypeLabel(strategy: Strategy): string {
  return strategy.strategy_type === "preset" ? "Template" : "Custom";
}

export function strategyTimeframeLabel(strategy: Strategy): string {
  const timeframe = strategy.timeframe ?? strategy.params?.timeframe;
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

export function compareStrategies(
  a: Strategy,
  b: Strategy,
  key: StrategySortKey,
  direction: SortDirection,
): number {
  let result = 0;
  switch (key) {
    case "name":
      result = a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
      break;
    case "timeframe":
      result = strategyTimeframeLabel(a).localeCompare(strategyTimeframeLabel(b), undefined, {
        sensitivity: "base",
      });
      break;
    case "type":
      result = strategyTypeLabel(a).localeCompare(strategyTypeLabel(b), undefined, {
        sensitivity: "base",
      });
      break;
    case "assetClass":
      result = a.asset_class_label.localeCompare(b.asset_class_label, undefined, {
        sensitivity: "base",
      });
      break;
    case "status":
      result = Number(b.enabled) - Number(a.enabled);
      break;
    case "backtest":
      result = backtestStatusLabel(normalizeBacktestStatus(a.backtest_status)).localeCompare(
        backtestStatusLabel(normalizeBacktestStatus(b.backtest_status)),
        undefined,
        { sensitivity: "base" },
      );
      break;
    case "trades":
      result = a.stats.total_trades - b.stats.total_trades;
      break;
    case "winRate":
      result = compareNullableNumber(a.stats.win_rate, b.stats.win_rate);
      break;
    case "pnl":
      result = a.stats.realized_pnl - b.stats.realized_pnl;
      break;
    case "open":
      result = a.stats.open_positions - b.stats.open_positions;
      break;
    case "lastTrade":
      result = compareNullableString(a.stats.last_trade_at, b.stats.last_trade_at);
      break;
    default:
      result = 0;
  }
  return direction === "asc" ? result : -result;
}

export function sortStrategies(
  strategies: Strategy[],
  key: StrategySortKey,
  direction: SortDirection,
): Strategy[] {
  return [...strategies].sort((a, b) => compareStrategies(a, b, key, direction));
}
