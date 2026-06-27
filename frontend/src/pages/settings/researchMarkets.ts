import type { ResearchScheduleMarket } from "../../api/client";
import { formatAppTimeOfDay, type TimeFormatOptions } from "../../lib/formatTime";

export const DEFAULT_DAILY_REPORT_MARKET_ID = "london";
export const DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS = -2;
export const DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS = -1;
export const DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS = 1;

export const MARKET_OFFSET_OPTIONS = Array.from({ length: 13 }, (_, index) => index - 6);

export function offsetLabel(hours: number): string {
  if (hours === 0) return "At market open";
  if (hours < 0) {
    const amount = Math.abs(hours);
    return `${amount} hour${amount === 1 ? "" : "s"} before open`;
  }
  return `${hours} hour${hours === 1 ? "" : "s"} after open`;
}

export function closeOffsetLabel(hours: number): string {
  if (hours === 0) return "At market close";
  if (hours < 0) {
    const amount = Math.abs(hours);
    return `${amount} hour${amount === 1 ? "" : "s"} before close`;
  }
  return `${hours} hour${hours === 1 ? "" : "s"} after close`;
}

function marketLocalDateParts(timezone: string, ref = new Date()): { y: number; m: number; d: number } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(ref);
  const get = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return { y: get("year"), m: get("month"), d: get("day") };
}

function localOpenInstantUtc(market: ResearchScheduleMarket, ref = new Date()): Date {
  const [openHour, openMinute] = market.open_time_local.split(":").map(Number);
  const { y, m, d } = marketLocalDateParts(market.timezone, ref);
  const guess = Date.UTC(y, m - 1, d, openHour, openMinute);

  for (let adjustMinutes = -16 * 60; adjustMinutes <= 16 * 60; adjustMinutes += 1) {
    const candidate = new Date(guess + adjustMinutes * 60_000);
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: market.timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(candidate);
    const get = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
    if (
      get("year") === y &&
      get("month") === m &&
      get("day") === d &&
      get("hour") === openHour &&
      get("minute") === openMinute
    ) {
      return candidate;
    }
  }

  return new Date(guess);
}

function localCloseInstantUtc(market: ResearchScheduleMarket, ref = new Date()): Date {
  const closeLocal = market.close_time_local ?? market.open_time_local;
  const [closeHour, closeMinute] = closeLocal.split(":").map(Number);
  const { y, m, d } = marketLocalDateParts(market.timezone, ref);
  const guess = Date.UTC(y, m - 1, d, closeHour, closeMinute);

  for (let adjustMinutes = -16 * 60; adjustMinutes <= 16 * 60; adjustMinutes += 1) {
    const candidate = new Date(guess + adjustMinutes * 60_000);
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: market.timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(candidate);
    const get = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
    if (
      get("year") === y &&
      get("month") === m &&
      get("day") === d &&
      get("hour") === closeHour &&
      get("minute") === closeMinute
    ) {
      return candidate;
    }
  }

  return new Date(guess);
}

function fridayOfWeek(ref = new Date()): Date {
  const day = ref.getUTCDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  const monday = new Date(ref);
  monday.setUTCDate(ref.getUTCDate() + mondayOffset);
  const friday = new Date(monday);
  friday.setUTCDate(monday.getUTCDate() + 4);
  return friday;
}

export function scheduledCloseRunUtc(
  market: ResearchScheduleMarket,
  offsetHours: number,
  ref = new Date(),
): Date {
  const closeUtc = localCloseInstantUtc(market, ref);
  return new Date(closeUtc.getTime() + offsetHours * 3_600_000);
}

export function scheduledWeeklyDebriefUtc(
  market: ResearchScheduleMarket,
  offsetHours: number,
  ref = new Date(),
): Date {
  const friday = fridayOfWeek(ref);
  return scheduledCloseRunUtc(market, offsetHours, friday);
}

export function scheduledRunUtc(
  market: ResearchScheduleMarket,
  offsetHours: number,
  ref = new Date(),
): Date {
  const openUtc = localOpenInstantUtc(market, ref);
  return new Date(openUtc.getTime() + offsetHours * 3_600_000);
}

export function formatUtcTime(date: Date, timeOptions?: TimeFormatOptions): string {
  if (timeOptions) {
    return formatAppTimeOfDay(date, timeOptions);
  }
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function schedulePreviewParts(
  market: ResearchScheduleMarket | undefined,
  offsetHours: number,
  ref = new Date(),
  timeOptions?: TimeFormatOptions,
): {
  runTimeUtc: string;
  offsetLabel: string;
  marketLabel: string;
  openTimeLocal: string;
  timezone: string;
} | null {
  if (!market) return null;
  const runUtc = scheduledRunUtc(market, offsetHours, ref);
  return {
    runTimeUtc: formatUtcTime(runUtc, timeOptions),
    offsetLabel: offsetLabel(offsetHours),
    marketLabel: market.label,
    openTimeLocal: market.open_time_local,
    timezone: market.timezone,
  };
}

export function closeSchedulePreviewParts(
  market: ResearchScheduleMarket | undefined,
  offsetHours: number,
  ref = new Date(),
  timeOptions?: TimeFormatOptions,
): {
  runTimeUtc: string;
  offsetLabel: string;
  marketLabel: string;
  closeTimeLocal: string;
  timezone: string;
} | null {
  if (!market) return null;
  const runUtc = scheduledWeeklyDebriefUtc(market, offsetHours, ref);
  const closeLocal = market.close_time_local ?? market.open_time_local;
  return {
    runTimeUtc: formatUtcTime(runUtc, timeOptions),
    offsetLabel: closeOffsetLabel(offsetHours),
    marketLabel: market.label,
    closeTimeLocal: closeLocal,
    timezone: market.timezone,
  };
}

export function describeSchedulePreview(
  market: ResearchScheduleMarket | undefined,
  offsetHours: number,
  timeOptions?: TimeFormatOptions,
): string | null {
  if (!market) return null;
  const runUtc = scheduledRunUtc(market, offsetHours);
  const runLabel = formatUtcTime(runUtc, timeOptions);
  return `${offsetLabel(offsetHours)} · ${market.label} opens ${market.open_time_local} · today ~${runLabel}`;
}

export function findScheduleMarket(
  markets: ResearchScheduleMarket[],
  marketId: string,
): ResearchScheduleMarket | undefined {
  return markets.find((market) => market.id === marketId);
}
