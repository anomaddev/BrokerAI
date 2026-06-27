import type { MarketSessionStatus, ResearchScheduleMarket, ResearchSettings } from "../api/client";
import type { OverallBotStatus } from "./bots";
import type { MarketIndicators } from "./displaySettings";
import { isMarketIndicatorEnabled } from "./displaySettings";
import { formatAppTimeOfDay, type TimeFormatOptions } from "./formatTime";
import { findEarliestNextMarketOpen, type MarketOpenTarget } from "./marketSessions";
import type { Timeframe } from "./strategyParams/types";
import { TIMEFRAME_LABELS } from "./strategyParams/types";

const DEFAULT_DAILY_REPORT_MARKET_ID = "london";
const DEFAULT_DAILY_REPORT_OFFSET_HOURS = -2;
const MIN_DAILY_REPORT_OFFSET_HOURS = -6;
const MAX_DAILY_REPORT_OFFSET_HOURS = 6;

/** Placeholder until live strategy timeframes drive candle updates. */
export const PLACEHOLDER_CANDLE_TIMEFRAME: Timeframe = "M15";

export type NextActionKind = "daily_report" | "market_open" | "candle_update" | "none";

export type LastActionKind = NextActionKind | "market_close";

export type LastActionState = {
  kind: LastActionKind;
  label: string;
  occurredAt: number;
};

export type NextActionState = {
  kind: NextActionKind;
  label: string;
  targetAt: number;
  windowStartAt: number;
  remainingMs: number;
  progress: number;
};

const FALLBACK_SCHEDULE_MARKETS: ResearchScheduleMarket[] = [
  {
    id: "london",
    name: "London",
    label: "London (LSE / FX)",
    timezone: "Europe/London",
    open_time_local: "08:00",
    close_time_local: "17:00",
  },
];

function normalizeMarketOffsetHours(offset: number | undefined): number {
  if (offset == null) return DEFAULT_DAILY_REPORT_OFFSET_HOURS;
  return Math.max(
    MIN_DAILY_REPORT_OFFSET_HOURS,
    Math.min(MAX_DAILY_REPORT_OFFSET_HOURS, Math.trunc(offset)),
  );
}

function addDaysIso(dateIso: string, days: number): string {
  const date = new Date(`${dateIso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function marketLocalDateIso(now: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

function getDateInTimezone(
  timeZone: string,
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
): Date {
  let utc = Date.UTC(year, month - 1, day, hour, minute, 0, 0);

  for (let attempt = 0; attempt < 4; attempt += 1) {
    const candidate = new Date(utc);
    const formatter = new Intl.DateTimeFormat("en-US", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    const parts = Object.fromEntries(
      formatter
        .formatToParts(candidate)
        .filter((part) => part.type !== "literal")
        .map((part) => [part.type, part.value]),
    );
    const gotYear = Number(parts.year);
    const gotMonth = Number(parts.month);
    const gotDay = Number(parts.day);
    const gotHour = Number(parts.hour === "24" ? "0" : parts.hour);
    const gotMinute = Number(parts.minute);

    if (
      gotYear === year &&
      gotMonth === month &&
      gotDay === day &&
      gotHour === hour &&
      gotMinute === minute
    ) {
      return candidate;
    }

    const desired = Date.UTC(year, month - 1, day, hour, minute);
    const actual = Date.UTC(gotYear, gotMonth - 1, gotDay, gotHour, gotMinute);
    utc += desired - actual;
  }

  return new Date(utc);
}

function marketOpenUtc(market: ResearchScheduleMarket, onDateIso: string): Date {
  const [year, month, day] = onDateIso.split("-").map(Number);
  const [hour, minute] = market.open_time_local.split(":").map(Number);
  return getDateInTimezone(market.timezone, year, month, day, hour, minute);
}

function scheduledDailyReportUtc(
  marketId: string,
  offsetHours: number,
  scheduleMarkets: ResearchScheduleMarket[],
  now: Date,
  onDateIso?: string,
): Date {
  const markets = scheduleMarkets.length > 0 ? scheduleMarkets : FALLBACK_SCHEDULE_MARKETS;
  const market =
    markets.find((entry) => entry.id === marketId) ??
    markets.find((entry) => entry.id === DEFAULT_DAILY_REPORT_MARKET_ID) ??
    markets[0];
  const offset = normalizeMarketOffsetHours(offsetHours);
  const localDate =
    onDateIso ?? marketLocalDateIso(now, market.timezone);
  const openAt = marketOpenUtc(market, localDate);
  return new Date(openAt.getTime() + offset * 60 * 60 * 1000);
}

function resolveDailyReportMarket(settings: ResearchSettings): ResearchScheduleMarket {
  const scheduleMarkets = settings.schedule_markets ?? FALLBACK_SCHEDULE_MARKETS;
  const marketId = settings.daily_report_market_id || DEFAULT_DAILY_REPORT_MARKET_ID;
  return (
    scheduleMarkets.find((entry) => entry.id === marketId) ??
    scheduleMarkets.find((entry) => entry.id === DEFAULT_DAILY_REPORT_MARKET_ID) ??
    scheduleMarkets[0]
  );
}

export function isOffMarketReportDate(dateIso: string): boolean {
  const day = new Date(`${dateIso}T12:00:00Z`).getUTCDay();
  return day === 0 || day === 6;
}

function nextPendingReportDateIso(settings: ResearchSettings, now: Date): string | null {
  const market = resolveDailyReportMarket(settings);
  const todayLocal = marketLocalDateIso(now, market.timezone);

  if (settings.last_daily_run_date !== todayLocal) {
    return todayLocal;
  }

  for (let dayOffset = 1; dayOffset <= 7; dayOffset += 1) {
    const candidate = addDaysIso(todayLocal, dayOffset);
    if (settings.last_daily_run_date !== candidate) {
      return candidate;
    }
  }

  return null;
}

function timeframeToMs(timeframe: Timeframe): number {
  const map: Record<Timeframe, number> = {
    M1: 60_000,
    M2: 120_000,
    M3: 180_000,
    M4: 240_000,
    M5: 300_000,
    M10: 600_000,
    M15: 900_000,
    M30: 1_800_000,
    H1: 3_600_000,
    H2: 7_200_000,
    H3: 10_800_000,
    H4: 14_400_000,
    H6: 21_600_000,
    H8: 28_800_000,
    H12: 43_200_000,
    D1: 86_400_000,
    W1: 604_800_000,
    MN: 2_592_000_000,
  };
  return map[timeframe];
}

export function formatCountdown(durationMs: number): string {
  const totalSeconds = Math.max(0, Math.ceil(durationMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function computeProgress(nowMs: number, startMs: number, targetMs: number): number {
  if (targetMs <= startMs) return 0;
  const total = targetMs - startMs;
  const remaining = Math.max(0, targetMs - nowMs);
  return Math.min(100, Math.max(0, (remaining / total) * 100));
}

function buildActionState(
  kind: NextActionKind,
  label: string,
  targetAt: number,
  windowStartAt: number,
  nowMs: number,
): NextActionState {
  const remainingMs = Math.max(0, targetAt - nowMs);
  return {
    kind,
    label,
    targetAt,
    windowStartAt,
    remainingMs,
    progress: computeProgress(nowMs, windowStartAt, targetAt),
  };
}

function computeDailyReportAction(
  settings: ResearchSettings,
  now: Date,
  reportDateIso?: string,
): NextActionState {
  const scheduleMarkets = settings.schedule_markets ?? FALLBACK_SCHEDULE_MARKETS;
  const marketId = settings.daily_report_market_id || DEFAULT_DAILY_REPORT_MARKET_ID;
  const offsetHours = settings.daily_report_market_offset_hours;

  const reportDate = reportDateIso ?? nextPendingReportDateIso(settings, now);
  if (!reportDate) {
    const nowMs = now.getTime();
    return buildActionState("daily_report", "Daily report", nowMs, nowMs, nowMs);
  }

  const target = scheduledDailyReportUtc(
    marketId,
    offsetHours,
    scheduleMarkets,
    now,
    reportDate,
  );
  const previousDate = addDaysIso(reportDate, -1);
  const windowStart = scheduledDailyReportUtc(
    marketId,
    offsetHours,
    scheduleMarkets,
    now,
    previousDate,
  ).getTime();
  const targetAt = target.getTime();
  const nowMs = now.getTime();

  return buildActionState(
    "daily_report",
    "Daily report",
    targetAt,
    windowStart,
    nowMs,
  );
}

function computeUpcomingDailyReportAction(
  settings: ResearchSettings,
  now: Date,
): NextActionState | null {
  const reportDate = nextPendingReportDateIso(settings, now);
  if (!reportDate) return null;
  return computeDailyReportAction(settings, now, reportDate);
}

function computeMarketOpenAction(
  sessions: MarketSessionStatus[],
  indicators: MarketIndicators,
  now: Date,
  options: { marketAvailable: boolean; serverTime?: string },
): NextActionState | null {
  const nextOpen = findEarliestNextMarketOpen(sessions, indicators, now, options);
  if (!nextOpen) return null;

  const nowMs = now.getTime();
  const targetAt = nextOpen.targetAt.getTime();
  const windowStartAt =
    nextOpen.windowStartAt?.getTime() ?? targetAt - 8 * 60 * 60 * 1000;

  return buildActionState(
    "market_open",
    `${nextOpen.sessionName} open`,
    targetAt,
    windowStartAt,
    nowMs,
  );
}

function computeCandleUpdateAction(now: Date, timeframe: Timeframe = PLACEHOLDER_CANDLE_TIMEFRAME): NextActionState {
  const durationMs = timeframeToMs(timeframe);
  const nowMs = now.getTime();
  const targetAt = Math.ceil(nowMs / durationMs) * durationMs;
  const windowStartAt = targetAt - durationMs;

  return buildActionState(
    "candle_update",
    `Next candle (${TIMEFRAME_LABELS[timeframe]})`,
    targetAt,
    windowStartAt,
    nowMs,
  );
}

export function computeNextAction(input: {
  marketsOpen: boolean;
  researchSettings: ResearchSettings | null;
  marketSessions: MarketSessionStatus[];
  marketIndicators: MarketIndicators;
  marketAvailable: boolean;
  marketServerTime?: string;
  now?: Date;
  candleTimeframe?: Timeframe | null;
}): NextActionState | null {
  const now = input.now ?? new Date();
  const nowMs = now.getTime();

  if (input.researchSettings?.daily_report_enabled) {
    const dailyAction = computeUpcomingDailyReportAction(input.researchSettings, now);
    if (dailyAction) {
      return dailyAction;
    }
  }

  if (input.marketsOpen) {
    if (input.candleTimeframe) {
      return computeCandleUpdateAction(now, input.candleTimeframe);
    }
    return computeCandleUpdateAction(now, PLACEHOLDER_CANDLE_TIMEFRAME);
  }

  const marketOpenAction = computeMarketOpenAction(
    input.marketSessions,
    input.marketIndicators,
    now,
    {
      marketAvailable: input.marketAvailable,
      serverTime: input.marketServerTime,
    },
  );
  if (marketOpenAction) return marketOpenAction;

  return buildActionState("none", "No upcoming action", nowMs + 60_000, nowMs, nowMs);
}

export function formatNextActionDisplay(action: NextActionState): string {
  if (action.kind === "daily_report") return "Daily Report";
  if (action.kind === "market_open") {
    const sessionName = action.label.replace(/\s+open$/i, "");
    return `${sessionName} Open`;
  }
  if (action.kind === "candle_update") {
    const match = action.label.match(/\(([^)]+)\)/);
    return match ? `Candle (${match[1]})` : "Candle Update";
  }
  return action.label;
}

export function formatNextActionTargetUtc(
  targetAt: number,
  nowMs = Date.now(),
  timeOptions?: TimeFormatOptions,
): string {
  if (timeOptions) {
    const target = new Date(targetAt);
    const now = new Date(nowMs);
    const sameDay =
      new Intl.DateTimeFormat("en-CA", {
        timeZone: timeOptions.showUtc ? "UTC" : timeOptions.timeZone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(target) ===
      new Intl.DateTimeFormat("en-CA", {
        timeZone: timeOptions.showUtc ? "UTC" : timeOptions.timeZone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(now);

    if (sameDay) {
      return formatAppTimeOfDay(target, timeOptions);
    }
    return formatAppTimeOfDay(target, timeOptions, true);
  }

  const target = new Date(targetAt);
  const now = new Date(nowMs);
  const time = new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(target);

  const sameUtcDay =
    target.getUTCFullYear() === now.getUTCFullYear() &&
    target.getUTCMonth() === now.getUTCMonth() &&
    target.getUTCDate() === now.getUTCDate();

  if (sameUtcDay) return `${time} UTC`;

  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return `${days[target.getUTCDay()]} ${time} UTC`;
}

export function resolveOverallStatusExplainer(
  status: OverallBotStatus,
  nextAction: NextActionState | null,
): string {
  if (status === "stopped") {
    return "Orchestrator is offline.";
  }

  if (status === "error") {
    return "One or more modules reported an error.";
  }

  if (nextAction?.kind === "daily_report") {
    return status === "running"
      ? "Daily report is due before the next scheduled action."
      : "Markets closed — daily report runs next.";
  }

  if (status === "running") {
    if (nextAction?.kind === "candle_update") {
      return "Markets open — waiting for the next candle close.";
    }
    return "Markets open — monitoring for updates.";
  }

  if (nextAction?.kind === "market_open") {
    return `Markets closed — waiting for ${nextAction.label.toLowerCase()}.`;
  }

  return "Markets closed — waiting for the next scheduled action.";
}

export type { MarketOpenTarget };
