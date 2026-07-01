import type { Trade } from "../api/client";
import { directionClassName, directionLabel } from "./strategyAnalysis";

const CLOSE_REASON_LABELS: Record<string, string> = {
  reverse_crossover: "Reverse crossover",
  trail_ema_slow: "Trail (EMA slow)",
  trail_atr: "Trail (ATR)",
  manual_close: "Manual close",
};

export function formatPrice(value: number | null | undefined): string {
  if (value == null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(5);
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

export function closeReasonLabel(reason: string | null | undefined): string {
  if (!reason) return "—";
  return CLOSE_REASON_LABELS[reason] ?? reason.replace(/_/g, " ");
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

export function analysisRunId(trade: Trade): string | null {
  const raw = trade.metadata?.analysis_run_id;
  return typeof raw === "string" && raw.trim() ? raw : null;
}

export function exploreHrefForTrade(trade: Trade): string {
  const params = new URLSearchParams({ pair: trade.pair });
  return `/trading/explore?${params.toString()}`;
}

export { directionClassName, directionLabel };
