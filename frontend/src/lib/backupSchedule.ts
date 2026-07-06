import type { ResearchScheduleMarket } from "../api/client";
import { nextDailyMarketRunUtc } from "../pages/settings/researchMarkets";
import { formatAppTimeOfDay, type TimeFormatOptions } from "./formatTime";

const DEFAULT_DAILY_TIME = "02:00";

export const BACKUP_INTERVAL_HOUR_OPTIONS = [6, 12, 24, 48] as const;
export const BACKUP_INTERVAL_HOURS_MAX = 48;

function addCalendarDays(parts: { y: number; m: number; d: number }, days: number): { y: number; m: number; d: number } {
  const date = new Date(Date.UTC(parts.y, parts.m - 1, parts.d + days));
  return { y: date.getUTCFullYear(), m: date.getUTCMonth() + 1, d: date.getUTCDate() };
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

function localInstantUtc(
  timezone: string,
  hour: number,
  minute: number,
  dateParts: { y: number; m: number; d: number },
): Date {
  const { y, m, d } = dateParts;
  const guess = Date.UTC(y, m - 1, d, hour, minute);

  for (let adjustMinutes = -16 * 60; adjustMinutes <= 16 * 60; adjustMinutes += 1) {
    const candidate = new Date(guess + adjustMinutes * 60_000);
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
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

export function normalizeDailyTime(value: string | null | undefined): string {
  if (!value?.trim()) return DEFAULT_DAILY_TIME;
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) return DEFAULT_DAILY_TIME;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return DEFAULT_DAILY_TIME;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function dateKeyInTimezone(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function addDaysToDateKey(dateKey: string, days: number): string {
  const [year, month, day] = dateKey.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "UTC",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(shifted);
}

export function formatRelativeScheduleDay(runUtc: Date, timeZone: string, ref = new Date()): string {
  const runKey = dateKeyInTimezone(runUtc, timeZone);
  const todayKey = dateKeyInTimezone(ref, timeZone);
  const tomorrowKey = addDaysToDateKey(todayKey, 1);

  if (runKey === todayKey) return "Today";
  if (runKey === tomorrowKey) return "Tomorrow";

  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    weekday: "long",
  }).format(runUtc);
}

export function nextDailyTimeRunUtc(
  dailyTime: string,
  timeZone: string,
  ref = new Date(),
): Date {
  const normalized = normalizeDailyTime(dailyTime);
  const [hour, minute] = normalized.split(":").map(Number);
  const dateParts = marketLocalDateParts(timeZone, ref);
  const runToday = localInstantUtc(timeZone, hour, minute, dateParts);
  if (ref.getTime() < runToday.getTime()) {
    return runToday;
  }
  return localInstantUtc(timeZone, hour, minute, addCalendarDays(dateParts, 1));
}

export function nextIntervalRunUtc(
  intervalHours: number,
  lastScheduledAt: string | null | undefined,
  ref = new Date(),
): Date {
  if (!lastScheduledAt) {
    return ref;
  }
  const last = new Date(lastScheduledAt);
  if (Number.isNaN(last.getTime())) {
    return ref;
  }
  const next = new Date(last.getTime() + intervalHours * 3_600_000);
  return next.getTime() > ref.getTime() ? next : ref;
}

export function formatBackupNextRunCallout(
  runUtc: Date,
  timeZone: string,
  timeOptions: TimeFormatOptions,
  ref = new Date(),
): { text: string; title?: string } {
  const day = formatRelativeScheduleDay(runUtc, timeZone, ref);
  const time = formatAppTimeOfDay(runUtc, timeOptions);
  const utcTime = formatAppTimeOfDay(runUtc, { ...timeOptions, showUtc: true, timeZone: "UTC" });
  return {
    text: `${day} at ${time}`,
    title: timeOptions.showUtc ? `${day} at ${time}` : `${day} at ${time} (${utcTime})`,
  };
}

export function backupScheduleNextRunCallout(
  settings: {
    mode?: string;
    daily_market_id?: string;
    daily_offset_hours?: number;
    daily_time?: string;
    interval_hours?: number;
    last_scheduled_at?: string | null;
  },
  context: {
    dailyMarket?: ResearchScheduleMarket;
    scheduleTimezone: string;
    timeOptions: TimeFormatOptions;
    ref?: Date;
  },
): { text: string; title?: string } | null {
  const ref = context.ref ?? new Date();
  const { timeOptions, scheduleTimezone } = context;

  if (settings.mode === "daily" && context.dailyMarket) {
    const runUtc = nextDailyMarketRunUtc(
      context.dailyMarket,
      settings.daily_offset_hours ?? 0,
      ref,
    );
    const callout = formatBackupNextRunCallout(runUtc, context.dailyMarket.timezone, timeOptions, ref);
    return {
      ...callout,
      title: `${callout.title ?? callout.text} · ${context.dailyMarket.label}`,
    };
  }

  if (settings.mode === "daily_time") {
    const runUtc = nextDailyTimeRunUtc(settings.daily_time ?? DEFAULT_DAILY_TIME, scheduleTimezone, ref);
    return formatBackupNextRunCallout(runUtc, scheduleTimezone, timeOptions, ref);
  }

  if (settings.mode === "interval") {
    const intervalHours = settings.interval_hours ?? 24;
    const runUtc = nextIntervalRunUtc(intervalHours, settings.last_scheduled_at, ref);
    return formatBackupNextRunCallout(runUtc, scheduleTimezone, timeOptions, ref);
  }

  return null;
}

export function backupDailyTimePreview(
  dailyTime: string,
  timeZone: string,
  timeOptions: TimeFormatOptions,
  ref = new Date(),
): { runTimeLocal: string; runTimeUtc: string; timezone: string } {
  const normalized = normalizeDailyTime(dailyTime);
  const [hour, minute] = normalized.split(":").map(Number);
  const dateParts = marketLocalDateParts(timeZone, ref);
  const runUtc = localInstantUtc(timeZone, hour, minute, dateParts);

  return {
    runTimeLocal: formatAppTimeOfDay(runUtc, timeOptions),
    runTimeUtc: formatAppTimeOfDay(runUtc, { ...timeOptions, showUtc: true, timeZone: "UTC" }),
    timezone: timeZone,
  };
}

export { DEFAULT_DAILY_TIME };

export const FULL_BACKUP_RETENTION = {
  min: 5,
  max: 50,
  step: 5,
  default: 30,
} as const;

export const CHANGE_BACKUP_RETENTION = {
  min: 20,
  max: 100,
  step: 5,
  default: 100,
} as const;

export function normalizeFullRetention(value: number | null | undefined): number {
  const { min, max, step, default: fallback } = FULL_BACKUP_RETENTION;
  const raw = Number.isFinite(value) ? Number(value) : fallback;
  const clamped = Math.min(max, Math.max(min, raw));
  const snapped = min + Math.round((clamped - min) / step) * step;
  return Math.min(max, Math.max(min, snapped));
}

export function normalizeChangeRetention(value: number | null | undefined): number {
  const { min, max, step, default: fallback } = CHANGE_BACKUP_RETENTION;
  const raw = Number.isFinite(value) ? Number(value) : fallback;
  const clamped = Math.min(max, Math.max(min, raw));
  const snapped = min + Math.round((clamped - min) / step) * step;
  return Math.min(max, Math.max(min, snapped));
}

export function normalizeIntervalHours(value: number | null | undefined): number {
  const fallback = 24;
  const raw = Number.isFinite(value) ? Number(value) : fallback;
  const clamped = Math.min(BACKUP_INTERVAL_HOURS_MAX, Math.max(1, raw));
  if (BACKUP_INTERVAL_HOUR_OPTIONS.includes(clamped as (typeof BACKUP_INTERVAL_HOUR_OPTIONS)[number])) {
    return clamped;
  }
  return BACKUP_INTERVAL_HOUR_OPTIONS.reduce((best, option) =>
    Math.abs(option - clamped) < Math.abs(best - clamped) ? option : best,
  );
}
