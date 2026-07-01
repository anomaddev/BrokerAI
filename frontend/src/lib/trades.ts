import type { Trade } from "../api/client";
import { directionClassName, directionLabel } from "./strategyAnalysis";
import { reasonCategoryLabel, tradeReasonPresentation } from "./tradeReasons";

export function formatPrice(value: number | null | undefined): string {
  if (value == null) return "—";
  return String(Number(value.toFixed(5)));
}

export function formatUnits(value: number | null | undefined): string {
  if (value == null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export function formatPnl(value: number | null | undefined): string {
  if (value == null) return "—";
  const formatted = Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (value > 0) return `+$${formatted}`;
  if (value < 0) return `-$${formatted}`;
  return "$0.00";
}

export function pnlClassName(value: number | null | undefined): string {
  if (value == null) return "";
  if (value > 0) return "trades-pnl trades-pnl--positive";
  if (value < 0) return "trades-pnl trades-pnl--negative";
  return "trades-pnl trades-pnl--neutral";
}

export function tradeStatusLabel(status: string): string {
  return status === "open" ? "Open" : "Closed";
}

export function tradeStatusClassName(status: string): string {
  if (status === "open") return "trades-status trades-status--open";
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
export function tradeLastModifiedAt(
  status: string,
  openedAt: string | null,
  closedAt: string | null | undefined,
): string | null {
  if (status === "open") return openedAt;
  return closedAt ?? null;
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
  if (trade.status !== "closed") return undefined;
  if (trade.exit_price != null) return trade.exit_price;
  return closeDetailsFromMetadata(trade.close_metadata).exit_price;
}

export function tradeRealizedPl(trade: Trade): number | null | undefined {
  if (trade.status !== "closed") return undefined;
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
