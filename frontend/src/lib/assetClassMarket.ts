import { formatForexDailyBreakNote, type TimeFormatOptions } from "./formatTime";
import { isForexDailyBreakSession, isForexOpen } from "./forexSchedule";

export type AssetClassMarketId = "forex" | "metals" | "crypto";

export type AssetClassMarketStatus = {
  id: AssetClassMarketId;
  name: string;
  status: "open" | "closed" | "break" | "stopped";
  hours: string;
};

export const ASSET_CLASS_MARKET_DEFS: Array<{
  id: AssetClassMarketId;
  name: string;
  hours: string;
}> = [
  {
    id: "forex",
    name: "Forex",
    hours: "Sun 22:00 – Fri 22:00 UTC",
  },
  {
    id: "metals",
    name: "Metals",
    hours: "Sun 22:00 – Fri 22:00 UTC",
  },
  {
    id: "crypto",
    name: "Crypto",
    hours: "24/7",
  },
];

function resolveFxMetalsStatus(
  reference: Date,
  options?: { fxOpen?: boolean },
): AssetClassMarketStatus["status"] {
  if (isForexDailyBreakSession(reference)) {
    return "break";
  }
  const apiAllows = options?.fxOpen ?? true;
  if (apiAllows && isForexOpen(reference)) {
    return "open";
  }
  return "closed";
}

export function buildAssetClassStatuses(
  reference: Date,
  options?: { fxOpen?: boolean },
): AssetClassMarketStatus[] {
  return ASSET_CLASS_MARKET_DEFS.map((def) => {
    if (def.id === "crypto") {
      return { ...def, status: "stopped" as const };
    }
    return {
      ...def,
      status: resolveFxMetalsStatus(reference, options),
    };
  });
}

export function assetClassLabel(status: AssetClassMarketStatus["status"]): string {
  if (status === "open") return "Open";
  if (status === "break") return "Break";
  if (status === "stopped") return "Stopped";
  return "Closed";
}

export function assetClassTone(
  status: AssetClassMarketStatus["status"],
): "open" | "closed" | "break" | "stopped" {
  if (status === "open") return "open";
  if (status === "break") return "break";
  if (status === "stopped") return "stopped";
  return "closed";
}

export function isAssetClassIndicatorVisible(assetClass: AssetClassMarketStatus): boolean {
  return assetClass.status !== "closed" && assetClass.status !== "stopped";
}

export function resolveAssetClassTooltip(
  assetClass: AssetClassMarketStatus,
  serverTime?: string,
  timeOptions?: TimeFormatOptions,
): { name: string; hours: string; timingLabel: string | null } {
  const when = serverTime ? new Date(serverTime) : new Date();
  const reference = Number.isNaN(when.getTime()) ? new Date() : when;

  if (assetClass.id === "crypto") {
    return {
      name: assetClass.name,
      hours: assetClass.hours,
      timingLabel: assetClass.status === "stopped" ? "Trading not enabled" : null,
    };
  }

  return {
    name: assetClass.name,
    hours: assetClass.hours,
    timingLabel: timeOptions
      ? formatForexDailyBreakNote(timeOptions, reference)
      : "Daily break 16:59–17:05 ET",
  };
}
