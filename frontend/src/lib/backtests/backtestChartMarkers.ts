import type { BacktestAction } from "../../api/client";
import { parseAppInstant } from "../formatTime";

export type BacktestChartMarkerRole = "entry" | "exit" | "skipped";

export type BacktestChartMarker = {
  id: string;
  sequence: number;
  time: number;
  price: number | null;
  direction: "long" | "short";
  role: BacktestChartMarkerRole;
  label: string;
  kind: string;
};

function toUnixSeconds(value: string | null | undefined): number | null {
  const date = parseAppInstant(value);
  if (!date) return null;
  return Math.floor(date.getTime() / 1000);
}

function metaNumber(meta: Record<string, unknown> | null | undefined, key: string): number | null {
  const raw = meta?.[key];
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string" && raw.trim()) {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function metaDirection(
  meta: Record<string, unknown> | null | undefined,
  message: string,
): "long" | "short" {
  const raw = String(meta?.direction || "").toLowerCase();
  if (raw === "long" || raw === "bullish" || raw === "buy") return "long";
  if (raw === "short" || raw === "bearish" || raw === "sell") return "short";
  const lower = message.toLowerCase();
  if (lower.includes("long") || lower.includes("buy") || lower.includes("bull")) return "long";
  if (lower.includes("short") || lower.includes("sell") || lower.includes("bear")) return "short";
  return "long";
}

function isExecutedSignal(action: BacktestAction): boolean {
  return action.message.toLowerCase().includes("executing trade");
}

function isSkippedSignal(action: BacktestAction): boolean {
  if (action.kind === "filter_fail") return true;
  if (action.kind !== "signal") return false;
  return !isExecutedSignal(action);
}

function exitLabel(kind: string, meta: Record<string, unknown> | null | undefined): string {
  if (kind === "sl") return "SL";
  if (kind === "tp") return "TP";
  const reason = String(meta?.reason || "").toLowerCase();
  if (reason.includes("stop")) return "SL";
  if (reason.includes("take") || reason.includes("tp")) return "TP";
  return "EXIT";
}

export type BacktestChartMarkerOptions = {
  /** Include FILTER / SKIP markers. Default false — they overwhelm multi-month charts. */
  includeSkipped?: boolean;
};

/**
 * Convert backtest action rows into chart markers.
 *
 * Default chart set is fills only (entry / exit / SL / TP). Skipped signals are
 * omitted unless ``includeSkipped`` is true, or the caller filters for a selected
 * skipped action separately.
 */
export function backtestActionsToChartMarkers(
  actions: BacktestAction[],
  options: BacktestChartMarkerOptions = {},
): BacktestChartMarker[] {
  const includeSkipped = Boolean(options.includeSkipped);
  const markers: BacktestChartMarker[] = [];

  for (const action of actions) {
    const time = toUnixSeconds(action.bar_time);
    if (time == null) continue;
    const meta = action.meta ?? null;
    const direction = metaDirection(meta, action.message);
    const price = metaNumber(meta, "price");
    const kind = action.kind.trim().toLowerCase();

    if (kind === "entry" || kind === "open") {
      markers.push({
        id: `entry-${action.sequence}`,
        sequence: action.sequence,
        time,
        price,
        direction,
        role: "entry",
        label: direction === "long" ? "LONG" : "SHORT",
        kind,
      });
      continue;
    }

    if (kind === "exit" || kind === "close" || kind === "sl" || kind === "tp") {
      markers.push({
        id: `exit-${action.sequence}`,
        sequence: action.sequence,
        time,
        price,
        direction,
        role: "exit",
        label: exitLabel(kind, meta),
        kind,
      });
      continue;
    }

    if (kind === "signal" && isExecutedSignal(action)) {
      continue;
    }

    if (includeSkipped && isSkippedSignal(action)) {
      markers.push({
        id: `skip-${action.sequence}`,
        sequence: action.sequence,
        time,
        price,
        direction,
        role: "skipped",
        label: kind === "filter_fail" ? "FILTER" : "SKIP",
        kind,
      });
    }
  }

  return markers;
}

/** Build the single marker for a selected skip/filter action so step-through can highlight it. */
export function backtestActionToSelectedMarker(
  action: BacktestAction | null | undefined,
): BacktestChartMarker | null {
  if (!action) return null;
  const markers = backtestActionsToChartMarkers([action], { includeSkipped: true });
  return markers[0] ?? null;
}
