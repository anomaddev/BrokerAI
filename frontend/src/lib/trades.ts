import type { ChildOrder, Trade, TradeReconciliation } from "../api/client";
import { directionClassName, directionLabel } from "./strategyAnalysis";
import { reasonCategoryLabel, tradeReasonPresentation } from "./tradeReasons";

function coerceNumber(value: unknown): number | null {
  if (value == null) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/** Resolve a display price from a ChildOrder or flat price field. */
export function orderPrice(
  order: ChildOrder | null | undefined,
  flatPrice?: number | null,
): number | null {
  const fromFlat = coerceNumber(flatPrice);
  if (fromFlat != null) return fromFlat;
  if (order == null) return null;
  return coerceNumber(order.price);
}

export function tradeStatusKey(
  trade: Pick<Trade, "state">,
): "open" | "closed" | "cancelled" {
  const raw = (trade.state ?? "closed").toLowerCase();
  if (raw === "open") return "open";
  if (raw === "cancelled") return "cancelled";
  return "closed";
}

export function tradeIsOpen(trade: Pick<Trade, "state">): boolean {
  return tradeStatusKey(trade) === "open";
}

export function tradeIsCancelled(trade: Pick<Trade, "state">): boolean {
  return tradeStatusKey(trade) === "cancelled";
}

export function formatPrice(value: unknown): string {
  const num = coerceNumber(value);
  if (num == null && value != null && typeof value === "object" && "price" in value) {
    return formatPrice((value as ChildOrder).price);
  }
  if (num == null) return "—";
  return String(Number(num.toFixed(5)));
}

export function formatUnits(value: unknown): string {
  const num = coerceNumber(value);
  if (num == null) return "—";
  return Number.isInteger(num) ? String(num) : num.toFixed(2);
}

export function formatPnl(value: unknown): string {
  const num = coerceNumber(value);
  if (num == null) return "—";
  const formatted = Math.abs(num).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (num > 0) return `+$${formatted}`;
  if (num < 0) return `-$${formatted}`;
  return "$0.00";
}

export function pnlClassName(value: unknown): string {
  const num = coerceNumber(value);
  if (num == null) return "";
  if (num > 0) return "trades-pnl trades-pnl--positive";
  if (num < 0) return "trades-pnl trades-pnl--negative";
  return "trades-pnl trades-pnl--neutral";
}

export function tradeStatusLabel(status: string): string {
  if (status === "open") return "Open";
  if (status === "cancelled") return "Cancelled";
  return "Closed";
}

export function tradeStatusClassName(status: string): string {
  if (status === "open") return "trades-status trades-status--open";
  if (status === "cancelled") return "trades-status trades-status--cancelled";
  return "trades-status trades-status--closed";
}

export function tradeReasonCell(trade: Trade): { display: string; title: string | undefined } {
  const { short, label, category } = tradeReasonPresentation(trade);
  if (!label || label === short) {
    return { display: short, title: undefined };
  }
  const categoryText = reasonCategoryLabel(category);
  const title = categoryText ? `${label} (${categoryText})` : label;
  return { display: short, title };
}

/** Open date for open trades; close date once closed. */
export type TradeTemporalFields = Pick<Trade, "state" | "open_time" | "close_time" | "updated_at">;

function firstPresentTimestamp(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return null;
}

/** Open date for open trades; close date once closed. */
export function tradeLastModifiedAt(
  statusOrTrade: string | TradeTemporalFields,
  openedAt?: string | null,
  closedAt?: string | null | undefined,
): string | null {
  if (typeof statusOrTrade === "string") {
    const status = statusOrTrade;
    if (status === "open") return openedAt ?? null;
    if (status === "cancelled") return closedAt ?? openedAt ?? null;
    return closedAt ?? null;
  }

  const trade = statusOrTrade;
  const status = tradeStatusKey(trade);
  if (status === "closed") {
    return firstPresentTimestamp(trade.close_time, trade.updated_at, trade.open_time);
  }
  if (status === "cancelled") {
    return firstPresentTimestamp(trade.close_time, trade.open_time, trade.updated_at);
  }
  return firstPresentTimestamp(trade.open_time, trade.updated_at);
}

export type TradeSortColumn =
  | "status"
  | "last_modified"
  | "strategy"
  | "pair"
  | "direction"
  | "entry"
  | "price"
  | "pnl"
  | "stop_loss"
  | "take_profit"
  | "units"
  | "reason"
  | "duration";

export type TradeSortDirection = "asc" | "desc";

export const DEFAULT_TRADE_SORT_COLUMN: TradeSortColumn = "last_modified";
export const DEFAULT_TRADE_SORT_DIRECTION: TradeSortDirection = "desc";

/** Default direction when a column header is first activated. */
export function defaultTradeSortDirection(column: TradeSortColumn): TradeSortDirection {
  if (
    column === "last_modified" ||
    column === "entry" ||
    column === "price" ||
    column === "pnl" ||
    column === "units" ||
    column === "duration"
  ) {
    return "desc";
  }
  return "asc";
}

function tradeStatusSortKey(trade: Pick<Trade, "state">): number {
  const status = tradeStatusKey(trade);
  if (status === "open") return 0;
  if (status === "closed") return 1;
  return 2;
}

function compareNullableNumbers(
  a: number | null | undefined,
  b: number | null | undefined,
): number {
  const aNum = coerceNumber(a);
  const bNum = coerceNumber(b);
  if (aNum == null && bNum == null) return 0;
  if (aNum == null) return 1;
  if (bNum == null) return -1;
  return aNum - bNum;
}

function compareNullableStrings(a: string | null | undefined, b: string | null | undefined): number {
  const aText = a?.trim() ?? "";
  const bText = b?.trim() ?? "";
  if (!aText && !bText) return 0;
  if (!aText) return 1;
  if (!bText) return -1;
  return aText.localeCompare(bText);
}

function tradePriceSortValue(
  trade: Trade,
  reconciliation?: TradeReconciliation | null,
): number | null {
  if (tradeIsOpen(trade)) {
    const fromReconciliation = coerceNumber(
      reconciliation?.ledger_market[trade.id]?.current_price,
    );
    if (fromReconciliation != null) return fromReconciliation;
    return coerceNumber(trade.entry_price);
  }
  return coerceNumber(tradeExitPrice(trade));
}

function tradePnlSortValue(
  trade: Trade,
  reconciliation?: TradeReconciliation | null,
): number | null {
  if (tradeIsOpen(trade)) {
    const fromReconciliation = coerceNumber(
      reconciliation?.ledger_market[trade.id]?.unrealized_pl,
    );
    if (fromReconciliation != null) return fromReconciliation;
    return coerceNumber(trade.unrealized_pl);
  }
  return coerceNumber(tradeRealizedPl(trade));
}

function tradeDurationSortKey(trade: Trade): number | null {
  if (tradeIsOpen(trade) || tradeIsCancelled(trade)) return null;
  if (!trade.open_time || !trade.close_time) return null;
  const start = Date.parse(trade.open_time);
  const end = Date.parse(trade.close_time);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return end - start;
}

/** Compare two trades by a single table column (ascending). */
export function compareTradesByColumn(
  a: Trade,
  b: Trade,
  column: TradeSortColumn,
  reconciliation?: TradeReconciliation | null,
): number {
  let primary = 0;
  switch (column) {
    case "status":
      primary = tradeStatusSortKey(a) - tradeStatusSortKey(b);
      break;
    case "last_modified":
      primary = compareNullableNumbers(
        tradeLastModifiedSortKey(a),
        tradeLastModifiedSortKey(b),
      );
      break;
    case "strategy":
      primary = compareNullableStrings(a.strategy_name, b.strategy_name);
      break;
    case "pair":
      primary = compareNullableStrings(a.pair, b.pair);
      break;
    case "direction":
      primary = compareNullableStrings(directionLabel(a.direction), directionLabel(b.direction));
      break;
    case "entry":
      primary = compareNullableNumbers(a.entry_price, b.entry_price);
      break;
    case "price":
      primary = compareNullableNumbers(
        tradePriceSortValue(a, reconciliation),
        tradePriceSortValue(b, reconciliation),
      );
      break;
    case "pnl":
      primary = compareNullableNumbers(
        tradePnlSortValue(a, reconciliation),
        tradePnlSortValue(b, reconciliation),
      );
      break;
    case "stop_loss":
      primary = compareNullableNumbers(
        orderPrice(a.stop_loss, a.stop_loss_price),
        orderPrice(b.stop_loss, b.stop_loss_price),
      );
      break;
    case "take_profit":
      primary = compareNullableNumbers(
        orderPrice(a.take_profit, a.take_profit_price),
        orderPrice(b.take_profit, b.take_profit_price),
      );
      break;
    case "units":
      primary = compareNullableNumbers(a.units, b.units);
      break;
    case "reason":
      primary = compareNullableStrings(
        tradeReasonCell(a).display,
        tradeReasonCell(b).display,
      );
      break;
    case "duration":
      primary = compareNullableNumbers(tradeDurationSortKey(a), tradeDurationSortKey(b));
      break;
    default:
      primary = 0;
  }

  if (primary !== 0) return primary;
  return compareNullableStrings(a.id, b.id);
}

function sortTradeSection(
  rows: Trade[],
  compare: (a: Trade, b: Trade) => number,
): Trade[] {
  return [...rows].sort(compare);
}

export type TradeStatusFilter = "all" | "open" | "closed";

/**
 * Sort trades for the table: open rows stay above non-open when showing all statuses;
 * column sort applies independently within each section.
 */
export function sortTradesForTable(
  trades: Trade[],
  options: {
    sortColumn: TradeSortColumn;
    sortDirection: TradeSortDirection;
    statusFilter: TradeStatusFilter;
    reconciliation?: TradeReconciliation | null;
  },
): Trade[] {
  const { sortColumn, sortDirection, statusFilter, reconciliation } = options;
  const directionMultiplier = sortDirection === "asc" ? 1 : -1;
  const compare = (a: Trade, b: Trade) =>
    directionMultiplier * compareTradesByColumn(a, b, sortColumn, reconciliation);

  if (statusFilter !== "all") {
    return sortTradeSection(trades, compare);
  }

  const openTrades = trades.filter((trade) => tradeIsOpen(trade));
  const nonOpenTrades = trades.filter((trade) => !tradeIsOpen(trade));
  return [...sortTradeSection(openTrades, compare), ...sortTradeSection(nonOpenTrades, compare)];
}

/** Compare trades for table display: open first, then newest last-modified within each group. */
export function compareTradesForDisplay(
  a: Pick<Trade, "state" | "open_time" | "close_time">,
  b: Pick<Trade, "state" | "open_time" | "close_time">,
): number {
  const aOpen = tradeStatusKey(a) === "open" ? 0 : tradeStatusKey(a) === "cancelled" ? 2 : 1;
  const bOpen = tradeStatusKey(b) === "open" ? 0 : tradeStatusKey(b) === "cancelled" ? 2 : 1;
  if (aOpen !== bOpen) return aOpen - bOpen;
  return tradeLastModifiedSortKey(b) - tradeLastModifiedSortKey(a);
}

/** Parse last-modified timestamp for sorting (ms since epoch). */
export function tradeLastModifiedSortKey(trade: TradeTemporalFields): number {
  const raw = tradeLastModifiedAt(trade);
  if (!raw) return 0;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function tradeDuration(openedAt: string | null, closedAt: string | null): string {
  if (!openedAt || !closedAt) return "—";
  const start = Date.parse(openedAt);
  const end = Date.parse(closedAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "—";
  const ms = end - start;
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rem = minutes % 60;
  if (hours < 24) return rem > 0 ? `${hours}h ${rem}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return remHours > 0 ? `${days}d ${remHours}h` : `${days}d`;
}

export function reconciliationBadgeLabel(badge: string | undefined): string {
  if (badge === "matched") return "Matched";
  if (badge === "ledger_only") return "Ledger only";
  return "";
}

export function reconciliationBadgeClassName(badge: string | undefined): string {
  if (badge === "matched") return "trades-badge trades-badge--matched";
  if (badge === "ledger_only") return "trades-badge trades-badge--ledger-only";
  return "";
}

export function reconciliationBannerClassName(
  status: "matched" | "mismatch" | "unconfigured",
): string {
  if (status === "matched") return "trades-reconcile-banner trades-reconcile-banner--ok";
  if (status === "mismatch") return "trades-reconcile-banner trades-reconcile-banner--warn";
  return "trades-reconcile-banner trades-reconcile-banner--muted";
}

export function reconciliationBannerText(
  reconciliation: {
    configured: boolean;
    mongo_open_count: number;
    broker_open_count: number;
    status: "matched" | "mismatch" | "unconfigured";
  },
): string {
  if (!reconciliation.configured) {
    return `Ledger: ${reconciliation.mongo_open_count} open trade(s). Connect OANDA to reconcile with your broker.`;
  }
  if (reconciliation.status === "matched") {
    return `Ledger and OANDA agree: ${reconciliation.mongo_open_count} open trade(s).`;
  }
  return `Reconciliation mismatch — BrokerAI ledger: ${reconciliation.mongo_open_count}, OANDA broker: ${reconciliation.broker_open_count}.`;
}

export function tradeExitPrice(trade: Trade): number | null | undefined {
  if (tradeIsOpen(trade)) return undefined;
  if (trade.exit_price != null) return trade.exit_price;
  return closeDetailsFromMetadata(trade.close_metadata).exit_price;
}

export function tradeRealizedPl(trade: Trade): number | null | undefined {
  if (tradeIsOpen(trade)) return undefined;
  if (trade.realized_pl != null) return trade.realized_pl;
  return closeDetailsFromMetadata(trade.close_metadata).realized_pl;
}

function closeDetailsFromMetadata(
  closeMetadata: Record<string, unknown> | undefined,
): { exit_price?: number | null; realized_pl?: number | null } {
  const brokerClose = closeMetadata?.broker_close;
  if (!brokerClose || typeof brokerClose !== "object") {
    return {};
  }
  const fill =
    (brokerClose as Record<string, unknown>).orderFillTransaction ??
    (brokerClose as Record<string, unknown>).orderCreateTransaction;
  if (!fill || typeof fill !== "object") {
    return {};
  }
  const fillObj = fill as Record<string, unknown>;
  const tradeClosed = fillObj.tradeClosed;
  const tradesClosed = Array.isArray(fillObj.tradesClosed) ? fillObj.tradesClosed : [];
  const firstClosed =
    tradeClosed && typeof tradeClosed === "object"
      ? (tradeClosed as Record<string, unknown>)
      : tradesClosed[0] && typeof tradesClosed[0] === "object"
        ? (tradesClosed[0] as Record<string, unknown>)
        : null;

  const exitPrice = optionalNumber(fillObj.price);
  let realizedPl = optionalNumber(fillObj.pl);
  if (realizedPl == null && firstClosed) {
    realizedPl = optionalNumber(firstClosed.realizedPL);
  }
  if (realizedPl == null && tradesClosed.length > 0) {
    let total = 0;
    let found = false;
    for (const entry of tradesClosed) {
      if (!entry || typeof entry !== "object") continue;
      const pl = optionalNumber((entry as Record<string, unknown>).realizedPL);
      if (pl != null) {
        total += pl;
        found = true;
      }
    }
    if (found) realizedPl = total;
  }

  return { exit_price: exitPrice, realized_pl: realizedPl };
}

function optionalNumber(value: unknown): number | null {
  if (value == null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function analysisRunId(trade: Trade): string | null {
  const raw = trade.metadata?.analysis_run_id;
  return typeof raw === "string" && raw.trim() ? raw : null;
}

export function exploreHrefForTrade(trade: Trade): string {
  const params = new URLSearchParams({ pair: trade.pair });
  return `/trading/explore?${params.toString()}`;
}

export { directionClassName, directionLabel };
