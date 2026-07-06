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

function addCalendarDays(parts: { y: number; m: number; d: number }, days: number): { y: number; m: number; d: number } {
  const date = new Date(Date.UTC(parts.y, parts.m - 1, parts.d + days));
  return { y: date.getUTCFullYear(), m: date.getUTCMonth() + 1, d: date.getUTCDate() };
}

export function nextDailyMarketRunUtc(
  market: ResearchScheduleMarket,
  offsetHours: number,
  ref = new Date(),
): Date {
  const runToday = scheduledRunUtc(market, offsetHours, ref);
  if (ref.getTime() < runToday.getTime()) {
    return runToday;
  }
  const tomorrow = addCalendarDays(marketLocalDateParts(market.timezone, ref), 1);
  const [openHour, openMinute] = market.open_time_local.split(":").map(Number);
  const openUtc = localInstantUtc(market, openHour, openMinute, tomorrow);
  return new Date(openUtc.getTime() + offsetHours * 3_600_000);
}

function marketLocalWeekday(timezone: string, ref = new Date()): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    weekday: "short",
  }).formatToParts(ref);
  const label = parts.find((part) => part.type === "weekday")?.value ?? "Mon";
  const map: Record<string, number> = {
    Mon: 0,
    Tue: 1,
    Wed: 2,
    Thu: 3,
    Fri: 4,
    Sat: 5,
    Sun: 6,
  };
  return map[label] ?? 0;
}

/** Monday (week open) for the weekly brief in the market's local calendar. */
export function weekOpenDateParts(timezone: string, ref = new Date()): { y: number; m: number; d: number } {
  const today = marketLocalDateParts(timezone, ref);
  const weekday = marketLocalWeekday(timezone, ref);
  if (weekday >= 5) {
    return addCalendarDays(today, 7 - weekday);
  }
  return addCalendarDays(today, -weekday);
}

function localInstantUtc(
  market: ResearchScheduleMarket,
  hour: number,
  minute: number,
  dateParts: { y: number; m: number; d: number },
): Date {
  const { y, m, d } = dateParts;
  const guess = Date.UTC(y, m - 1, d, hour, minute);

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
      get("hour") === hour &&
      get("minute") === minute
    ) {
      return candidate;
    }
  }

  return new Date(guess);
}

function localOpenInstantUtc(market: ResearchScheduleMarket, ref = new Date()): Date {
  const [openHour, openMinute] = market.open_time_local.split(":").map(Number);
  const dateParts = marketLocalDateParts(market.timezone, ref);
  return localInstantUtc(market, openHour, openMinute, dateParts);
}

/** Market dropdown label with open time in UTC or the market timezone. */
export function formatScheduleMarketOptionLabel(
  market: ResearchScheduleMarket,
  timeOptions: TimeFormatOptions,
  ref = new Date(),
): string {
  const openUtc = localOpenInstantUtc(market, ref);
  const displayOptions: TimeFormatOptions = timeOptions.showUtc
    ? { ...timeOptions, showUtc: true, timeZone: "UTC" }
    : { ...timeOptions, showUtc: false, timeZone: market.timezone };
  const openTime = formatAppTimeOfDay(openUtc, displayOptions);
  return `${market.label} · opens ${openTime}`;
}

/** Friday (week end) for the weekly debrief in the market's local calendar. */
export function weekEndCloseDateParts(timezone: string, ref = new Date()): { y: number; m: number; d: number } {
  return addCalendarDays(weekOpenDateParts(timezone, ref), 4);
}

function scheduledWeeklyDebriefRunUtc(
  market: ResearchScheduleMarket,
  offsetHours: number,
  ref = new Date(),
): Date {
  const closeDay = weekEndCloseDateParts(market.timezone, ref);
  const closeLocal = market.close_time_local ?? market.open_time_local;
  const [closeHour, closeMinute] = closeLocal.split(":").map(Number);
  const closeUtc = localInstantUtc(market, closeHour, closeMinute, closeDay);
  return new Date(closeUtc.getTime() + offsetHours * 3_600_000);
}

export function nextWeeklyDebriefRunUtc(
  market: ResearchScheduleMarket,
  offsetHours: number,
  ref = new Date(),
): Date {
  const scheduled = scheduledWeeklyDebriefRunUtc(market, offsetHours, ref);
  if (ref.getTime() >= scheduled.getTime()) {
    const nextCloseDay = addCalendarDays(weekEndCloseDateParts(market.timezone, ref), 7);
    const closeLocal = market.close_time_local ?? market.open_time_local;
    const [closeHour, closeMinute] = closeLocal.split(":").map(Number);
    const closeUtc = localInstantUtc(market, closeHour, closeMinute, nextCloseDay);
    return new Date(closeUtc.getTime() + offsetHours * 3_600_000);
  }
  return scheduled;
}

function nextWeeklyDebriefCloseDateParts(
  market: ResearchScheduleMarket,
  offsetHours: number,
  ref = new Date(),
): { y: number; m: number; d: number } {
  const closeDay = weekEndCloseDateParts(market.timezone, ref);
  if (ref.getTime() >= scheduledWeeklyDebriefRunUtc(market, offsetHours, ref).getTime()) {
    return addCalendarDays(closeDay, 7);
  }
  return closeDay;
}

export function scheduledRunUtc(
  market: ResearchScheduleMarket,
  offsetHours: number,
  ref = new Date(),
): Date {
  const openUtc = localOpenInstantUtc(market, ref);
  return new Date(openUtc.getTime() + offsetHours * 3_600_000);
}

export function scheduledWeeklyBriefRunUtc(
  market: ResearchScheduleMarket,
  offsetHours: number,
  ref = new Date(),
): Date {
  const [openHour, openMinute] = market.open_time_local.split(":").map(Number);
  const openDay = weekOpenDateParts(market.timezone, ref);
  const openUtc = localInstantUtc(market, openHour, openMinute, openDay);
  return new Date(openUtc.getTime() + offsetHours * 3_600_000);
}

export function nextWeeklyBriefRunUtc(
  market: ResearchScheduleMarket,
  offsetHours: number,
  ref = new Date(),
): Date {
  const scheduled = scheduledWeeklyBriefRunUtc(market, offsetHours, ref);
  if (ref.getTime() >= scheduled.getTime()) {
    const nextOpenDay = addCalendarDays(weekOpenDateParts(market.timezone, ref), 7);
    const [openHour, openMinute] = market.open_time_local.split(":").map(Number);
    const openUtc = localInstantUtc(market, openHour, openMinute, nextOpenDay);
    return new Date(openUtc.getTime() + offsetHours * 3_600_000);
  }
  return scheduled;
}

function formatLocalDate(parts: { y: number; m: number; d: number }): string {
  const month = String(parts.m).padStart(2, "0");
  const day = String(parts.d).padStart(2, "0");
  return `${parts.y}-${month}-${day}`;
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

export function weeklyBriefSchedulePreviewParts(
  market: ResearchScheduleMarket | undefined,
  offsetHours: number,
  ref = new Date(),
  timeOptions?: TimeFormatOptions,
): {
  runTimeUtc: string;
  runDate: string;
  offsetLabel: string;
  marketLabel: string;
  openTimeLocal: string;
  timezone: string;
} | null {
  if (!market) return null;
  const runUtc = nextWeeklyBriefRunUtc(market, offsetHours, ref);
  const openDay = weekOpenDateParts(market.timezone, ref);
  const runDate =
    ref.getTime() >= scheduledWeeklyBriefRunUtc(market, offsetHours, ref).getTime()
      ? formatLocalDate(addCalendarDays(openDay, 7))
      : formatLocalDate(openDay);
  return {
    runTimeUtc: formatUtcTime(runUtc, timeOptions),
    runDate,
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
  runDate: string;
  offsetLabel: string;
  marketLabel: string;
  closeTimeLocal: string;
  timezone: string;
} | null {
  if (!market) return null;
  const runUtc = nextWeeklyDebriefRunUtc(market, offsetHours, ref);
  const closeDay = nextWeeklyDebriefCloseDateParts(market, offsetHours, ref);
  const closeLocal = market.close_time_local ?? market.open_time_local;
  return {
    runTimeUtc: formatUtcTime(runUtc, timeOptions),
    runDate: formatLocalDate(closeDay),
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

export function describeWeeklyBriefSchedulePreview(
  market: ResearchScheduleMarket | undefined,
  offsetHours: number,
  timeOptions?: TimeFormatOptions,
): string | null {
  const preview = weeklyBriefSchedulePreviewParts(market, offsetHours, new Date(), timeOptions);
  if (!preview) return null;
  return `${preview.offsetLabel} · ${preview.marketLabel} opens ${preview.openTimeLocal} · ~${preview.runTimeUtc} · ${preview.runDate}`;
}

export function findScheduleMarket(
  markets: ResearchScheduleMarket[],
  marketId: string,
): ResearchScheduleMarket | undefined {
  return markets.find((market) => market.id === marketId);
}
