import type { SessionDef } from "./marketSessionDefs";

export type TimeFormatOptions = {
  showUtc: boolean;
  timeZone: string;
};

export type AppInstantStyle = "full" | "short" | "compact";

function parseInstant(value: string | number | Date): Date | null {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }

  if (typeof value === "number") {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const trimmed = value.trim();
  if (!trimmed) return null;

  const utcMatch = trimmed.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::\d{2})?\s*UTC$/i);
  if (utcMatch) {
    const date = new Date(`${utcMatch[1]}T${utcMatch[2]}:00Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const date = new Date(trimmed);
  return Number.isNaN(date.getTime()) ? null : date;
}

function effectiveTimeZone(options: TimeFormatOptions): string {
  return options.showUtc ? "UTC" : options.timeZone;
}

function timezoneSuffix(options: TimeFormatOptions): string {
  if (options.showUtc) return " UTC";
  try {
    const parts = new Intl.DateTimeFormat(undefined, {
      timeZone: options.timeZone,
      timeZoneName: "short",
    }).formatToParts(new Date());
    const name = parts.find((part) => part.type === "timeZoneName")?.value;
    return name ? ` ${name}` : "";
  } catch {
    return "";
  }
}

export function formatAppInstant(
  value: string | number | Date | null | undefined,
  options: TimeFormatOptions,
  style: AppInstantStyle = "full",
): string {
  if (value == null) return "—";
  const date = parseInstant(value);
  if (!date) return typeof value === "string" ? value : "—";

  const timeZone = effectiveTimeZone(options);

  if (style === "short") {
    const formatted = new Intl.DateTimeFormat(undefined, {
      timeZone,
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
    return `${formatted}${timezoneSuffix(options)}`;
  }

  if (style === "compact") {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      month: "2-digit",
      day: "2-digit",
      year: "2-digit",
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
      hour12: true,
      timeZoneName: options.showUtc ? undefined : "short",
    }).formatToParts(date);

    const part = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find((entry) => entry.type === type)?.value ?? "";

    const tz = options.showUtc ? "UTC" : part("timeZoneName");
    return `${part("month")}-${part("day")}-${part("year")} at ${part("hour")}:${part("minute")}:${part("second")} ${part("dayPeriod")}${tz ? ` ${tz}` : ""}`;
  }

  const formatted = new Intl.DateTimeFormat(undefined, {
    timeZone,
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
  return `${formatted}${timezoneSuffix(options)}`;
}

export function formatAppTimeOfDay(
  value: string | number | Date,
  options: TimeFormatOptions,
  includeWeekday = false,
): string {
  const date = parseInstant(value);
  if (!date) return "—";

  const timeZone = effectiveTimeZone(options);
  const time = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);

  if (!includeWeekday) {
    return `${time}${timezoneSuffix(options)}`;
  }

  const weekday = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    weekday: "short",
  }).format(date);
  return `${weekday} ${time}${timezoneSuffix(options)}`;
}

function utcTimeOnReference(
  hour: number,
  minute: number,
  reference: Date,
): Date {
  return new Date(
    Date.UTC(
      reference.getUTCFullYear(),
      reference.getUTCMonth(),
      reference.getUTCDate(),
      hour,
      minute,
    ),
  );
}

export function formatSessionHours(
  def: Pick<SessionDef, "startHour" | "startMinute" | "endHour" | "endMinute">,
  options: TimeFormatOptions,
  reference = new Date(),
): string {
  const start = utcTimeOnReference(def.startHour, def.startMinute, reference);
  const end = utcTimeOnReference(def.endHour, def.endMinute, reference);

  const startLabel = formatAppTimeOfDay(start, options).replace(/\s*(UTC|[A-Z]{2,5})$/i, "");
  const endLabel = formatAppTimeOfDay(end, options).replace(/\s*(UTC|[A-Z]{2,5})$/i, "");
  const suffix = timezoneSuffix(options);

  return `${startLabel}–${endLabel}${suffix}`;
}

const FOREX_SCHEDULE_ZONE = "America/New_York";

function calendarDateInZone(
  timeZone: string,
  reference: Date,
): { year: number; month: number; day: number } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(reference);
  return {
    year: Number(parts.find((part) => part.type === "year")?.value),
    month: Number(parts.find((part) => part.type === "month")?.value),
    day: Number(parts.find((part) => part.type === "day")?.value),
  };
}

function clockInZone(
  timeZone: string,
  reference: Date,
  hour: number,
  minute: number,
): Date {
  const { year, month, day } = calendarDateInZone(timeZone, reference);
  let guessMs = Date.UTC(year, month - 1, day, hour, minute);

  for (let attempt = 0; attempt < 4; attempt += 1) {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(new Date(guessMs));

    const actualYear = Number(parts.find((part) => part.type === "year")?.value);
    const actualMonth = Number(parts.find((part) => part.type === "month")?.value);
    const actualDay = Number(parts.find((part) => part.type === "day")?.value);
    const actualHour = Number(parts.find((part) => part.type === "hour")?.value);
    const actualMinute = Number(parts.find((part) => part.type === "minute")?.value);

    if (
      actualYear === year &&
      actualMonth === month &&
      actualDay === day &&
      actualHour === hour &&
      actualMinute === minute
    ) {
      return new Date(guessMs);
    }

    const targetMinutes = hour * 60 + minute;
    const actualMinutes = actualHour * 60 + actualMinute;
    guessMs += (targetMinutes - actualMinutes) * 60_000;
    guessMs +=
      Date.UTC(year, month - 1, day) - Date.UTC(actualYear, actualMonth - 1, actualDay);
  }

  return new Date(guessMs);
}

/** OANDA forex/metals daily maintenance window (16:59–17:05 America/New_York). */
export function formatForexDailyBreakNote(
  options: TimeFormatOptions,
  reference = new Date(),
): string {
  const start = clockInZone(FOREX_SCHEDULE_ZONE, reference, 16, 59);
  const end = clockInZone(FOREX_SCHEDULE_ZONE, reference, 17, 5);
  const startLabel = formatAppTimeOfDay(start, options).replace(/\s*(UTC|[A-Z]{2,5})$/i, "");
  const endLabel = formatAppTimeOfDay(end, options).replace(/\s*(UTC|[A-Z]{2,5})$/i, "");
  return `Daily break ${startLabel}–${endLabel}${timezoneSuffix(options)}`;
}

export function parseAppInstant(value: string | number | Date | null | undefined): Date | null {
  if (value == null) return null;
  return parseInstant(value);
}

export function createChartTimeFormatter(options: TimeFormatOptions) {
  const timeZone = effectiveTimeZone(options);

  return (timestamp: number) => {
    const date = new Date(timestamp * 1000);
    const formatted = new Intl.DateTimeFormat(undefined, {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
    return options.showUtc ? `${formatted} UTC` : formatted;
  };
}

export function createChartDateFormatter(options: TimeFormatOptions) {
  const timeZone = effectiveTimeZone(options);

  return (timestamp: number) =>
    new Intl.DateTimeFormat(undefined, {
      timeZone,
      month: "short",
      day: "numeric",
    }).format(new Date(timestamp * 1000));
}
