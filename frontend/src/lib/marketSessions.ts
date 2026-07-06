import type { MarketSessionStatus } from "../api/client";
import { formatAppTimeOfDay, formatSessionHours, type TimeFormatOptions } from "./formatTime";
import { isMarketIndicatorEnabled, type MarketIndicators } from "./displaySettings";
import {
  hasEnabledForexTradingSessions,
  isForexTradingSessionEnabled,
  type ForexTradingSessions,
} from "./forexTradingSessions";
import { isForexOpen } from "./forexSchedule";
import {
  MARKET_SESSION_DEFS,
  SESSION_BY_ID,
  type SessionDef,
} from "./marketSessionDefs";

export { MARKET_SESSION_DEFS, SESSION_OPTIONS, type SessionDef } from "./marketSessionDefs";

function localMinutes(def: SessionDef, when: Date): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: def.timezone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(when);

  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? 0);
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? 0);
  return hour * 60 + minute;
}

function calendarDateInZone(timeZone: string, reference: Date): { y: number; m: number; d: number } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(reference);
  return {
    y: Number(parts.find((part) => part.type === "year")?.value ?? 0),
    m: Number(parts.find((part) => part.type === "month")?.value ?? 0),
    d: Number(parts.find((part) => part.type === "day")?.value ?? 0),
  };
}

function clockInZone(timeZone: string, reference: Date, hour: number, minute: number): Date {
  const { y, m, d } = calendarDateInZone(timeZone, reference);
  let guessMs = Date.UTC(y, m - 1, d, hour, minute);

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
      actualYear === y &&
      actualMonth === m &&
      actualDay === d &&
      actualHour === hour &&
      actualMinute === minute
    ) {
      return new Date(guessMs);
    }

    const targetMinutes = hour * 60 + minute;
    const actualMinutes = actualHour * 60 + actualMinute;
    guessMs += (targetMinutes - actualMinutes) * 60_000;
    guessMs += Date.UTC(y, m - 1, d) - Date.UTC(actualYear, actualMonth - 1, actualDay);
  }

  return new Date(guessMs);
}

function addCalendarDays(parts: { y: number; m: number; d: number }, days: number): Date {
  const date = new Date(Date.UTC(parts.y, parts.m - 1, parts.d + days));
  return date;
}

function isSessionActive(def: SessionDef, when: Date): boolean {
  const current = localMinutes(def, when);
  const start = def.startHour * 60 + def.startMinute;
  const end = def.endHour * 60 + def.endMinute;
  if (start <= end) {
    return start <= current && current < end;
  }
  return current >= start || current < end;
}

function formatUtcTime(date: Date): string {
  return `${String(date.getUTCHours()).padStart(2, "0")}:${String(date.getUTCMinutes()).padStart(2, "0")} UTC`;
}

function formatUtcOpen(date: Date): string {
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return `${days[date.getUTCDay()]} ${formatUtcTime(date)}`;
}

function formatTimeOfDay(date: Date, options?: TimeFormatOptions, includeWeekday = false): string {
  if (options) {
    return formatAppTimeOfDay(date, options, includeWeekday);
  }
  return includeWeekday ? formatUtcOpen(date) : formatUtcTime(date);
}

function sessionHoursLabel(
  def: SessionDef,
  options?: TimeFormatOptions,
  reference?: Date,
): string {
  if (options && def) {
    return formatSessionHours(def, options, reference);
  }
  return def.hours;
}

function sessionOpenAt(def: SessionDef, reference: Date): Date {
  return clockInZone(def.timezone, reference, def.startHour, def.startMinute);
}

function sessionCloseAt(def: SessionDef, reference: Date): Date {
  const start = def.startHour * 60 + def.startMinute;
  const end = def.endHour * 60 + def.endMinute;
  const current = localMinutes(def, reference);

  if (start > end && current >= start) {
    const { y, m, d } = calendarDateInZone(def.timezone, reference);
    const nextDay = addCalendarDays({ y, m, d }, 1);
    return clockInZone(def.timezone, nextDay, def.endHour, def.endMinute);
  }

  return clockInZone(def.timezone, reference, def.endHour, def.endMinute);
}

function nextSessionOpen(def: SessionDef, from: Date): Date | null {
  const { y, m, d } = calendarDateInZone(def.timezone, from);
  for (let dayOffset = 0; dayOffset < 8; dayOffset += 1) {
    const dayRef = addCalendarDays({ y, m, d }, dayOffset);
    const openAt = clockInZone(def.timezone, dayRef, def.startHour, def.startMinute);
    if (openAt <= from) continue;
    if (!isForexOpen(openAt)) continue;
    return openAt;
  }
  return null;
}

function previousSessionClose(def: SessionDef, before: Date): Date | null {
  const { y, m, d } = calendarDateInZone(def.timezone, before);
  for (let dayOffset = 0; dayOffset < 8; dayOffset += 1) {
    const dayRef = addCalendarDays({ y, m, d }, -dayOffset);
    const closeAt = clockInZone(def.timezone, dayRef, def.endHour, def.endMinute);
    if (closeAt < before && isForexOpen(closeAt)) {
      return closeAt;
    }
    const start = def.startHour * 60 + def.startMinute;
    const end = def.endHour * 60 + def.endMinute;
    if (start > end) {
      const wrapClose = clockInZone(def.timezone, addCalendarDays(calendarDateInZone(def.timezone, dayRef), 1), def.endHour, def.endMinute);
      if (wrapClose < before && isForexOpen(wrapClose)) {
        return wrapClose;
      }
    }
  }
  return null;
}

export type MarketOpenTarget = {
  sessionId: string;
  sessionName: string;
  targetAt: Date;
  windowStartAt: Date | null;
};

function resolveSessionNextOpen(
  session: MarketSessionStatus,
  reference: Date,
): Date | null {
  if (session.next_open) {
    const parsed = new Date(session.next_open);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }

  const def = SESSION_BY_ID[session.id];
  return def ? nextSessionOpen(def, reference) : null;
}

function resolveSessionWindowStart(
  session: MarketSessionStatus,
  reference: Date,
  targetAt: Date,
): Date | null {
  if (session.closes_at) {
    const parsed = new Date(session.closes_at);
    if (!Number.isNaN(parsed.getTime()) && parsed.getTime() < targetAt.getTime()) {
      return parsed;
    }
  }

  const def = SESSION_BY_ID[session.id];
  if (!def) return null;
  return previousSessionClose(def, targetAt);
}

function findEarliestNextOpen(
  sessions: MarketSessionStatus[],
  isSessionEnabled: (sessionId: string) => boolean,
  hasAnyEnabled: boolean,
  now: Date,
  options?: { marketAvailable?: boolean; serverTime?: string },
): MarketOpenTarget | null {
  if (!hasAnyEnabled) return null;

  const useLocalFallback = options?.marketAvailable === false || sessions.length === 0;
  const when = options?.serverTime ? new Date(options.serverTime) : now;
  const reference = Number.isNaN(when.getTime()) ? now : when;
  const activeSessions = useLocalFallback ? buildLocalSessionStatuses(reference) : sessions;

  let earliest: MarketOpenTarget | null = null;

  for (const session of activeSessions) {
    if (!isSessionEnabled(session.id)) continue;
    if (session.status === "open") continue;

    const targetAt = resolveSessionNextOpen(session, reference);
    if (!targetAt || targetAt.getTime() <= reference.getTime()) continue;

    if (earliest && targetAt.getTime() >= earliest.targetAt.getTime()) continue;

    earliest = {
      sessionId: session.id,
      sessionName: session.name || SESSION_BY_ID[session.id]?.name || session.id,
      targetAt,
      windowStartAt: resolveSessionWindowStart(session, reference, targetAt),
    };
  }

  return earliest;
}

export function findEarliestNextMarketOpen(
  sessions: MarketSessionStatus[],
  indicators: MarketIndicators,
  now: Date,
  options?: { marketAvailable?: boolean; serverTime?: string },
): MarketOpenTarget | null {
  return findEarliestNextOpen(
    sessions,
    (sessionId) => isMarketIndicatorEnabled(indicators, sessionId),
    Object.values(indicators).some(Boolean),
    now,
    options,
  );
}

export function findEarliestNextTradingSessionOpen(
  sessions: MarketSessionStatus[],
  enabledSessions: ForexTradingSessions,
  now: Date,
  options?: { marketAvailable?: boolean; serverTime?: string },
): MarketOpenTarget | null {
  return findEarliestNextOpen(
    sessions,
    (sessionId) => isForexTradingSessionEnabled(enabledSessions, sessionId),
    hasEnabledForexTradingSessions(enabledSessions),
    now,
    options,
  );
}

export type MarketCloseEvent = {
  sessionId: string;
  sessionName: string;
  closedAt: Date;
};

export type MarketSessionOpenEvent = {
  sessionId: string;
  sessionName: string;
  openedAt: Date;
};

export function findLatestMarketClose(
  sessions: MarketSessionStatus[],
  indicators: MarketIndicators,
  now: Date,
  options?: { marketAvailable?: boolean; serverTime?: string },
): MarketCloseEvent | null {
  const hasEnabledIndicators = Object.values(indicators).some(Boolean);
  if (!hasEnabledIndicators) return null;

  const useLocalFallback = options?.marketAvailable === false || sessions.length === 0;
  const when = options?.serverTime ? new Date(options.serverTime) : now;
  const reference = Number.isNaN(when.getTime()) ? now : when;
  const activeSessions = useLocalFallback ? buildLocalSessionStatuses(reference) : sessions;

  let latest: MarketCloseEvent | null = null;

  for (const session of activeSessions) {
    if (!isMarketIndicatorEnabled(indicators, session.id)) continue;
    if (session.status === "open") continue;

    const def = SESSION_BY_ID[session.id];
    const closedAt = def ? previousSessionClose(def, reference) : null;
    if (!closedAt || closedAt.getTime() > reference.getTime()) continue;

    if (!latest || closedAt.getTime() > latest.closedAt.getTime()) {
      latest = {
        sessionId: session.id,
        sessionName: session.name || def?.name || session.id,
        closedAt,
      };
    }
  }

  return latest;
}

export function findLatestSessionOpen(
  sessions: MarketSessionStatus[],
  indicators: MarketIndicators,
  now: Date,
  options?: { marketAvailable?: boolean; serverTime?: string },
): MarketSessionOpenEvent | null {
  const hasEnabledIndicators = Object.values(indicators).some(Boolean);
  if (!hasEnabledIndicators) return null;

  const useLocalFallback = options?.marketAvailable === false || sessions.length === 0;
  const when = options?.serverTime ? new Date(options.serverTime) : now;
  const reference = Number.isNaN(when.getTime()) ? now : when;
  const activeSessions = useLocalFallback ? buildLocalSessionStatuses(reference) : sessions;

  let latest: MarketSessionOpenEvent | null = null;

  for (const session of activeSessions) {
    if (!isMarketIndicatorEnabled(indicators, session.id)) continue;
    if (session.status !== "open") continue;

    const def = SESSION_BY_ID[session.id];
    if (!def || !isSessionActive(def, reference)) continue;

    const openedAt = sessionOpenAt(def, reference);
    if (openedAt.getTime() > reference.getTime()) continue;

    if (!latest || openedAt.getTime() > latest.openedAt.getTime()) {
      latest = {
        sessionId: session.id,
        sessionName: session.name || def.name,
        openedAt,
      };
    }
  }

  return latest;
}

function currentSessionClose(def: SessionDef, from: Date): Date | null {
  if (!isSessionActive(def, from) || !isForexOpen(from)) return null;
  const closeAt = sessionCloseAt(def, from);
  return closeAt > from ? closeAt : null;
}

export function resolveSessionTooltip(
  session: MarketSessionStatus,
  serverTime?: string,
  timeOptions?: TimeFormatOptions,
): { name: string; hours: string; timingLabel: string | null } {
  const def = SESSION_BY_ID[session.id];
  const name = session.name || def?.name || session.id;
  const when = serverTime ? new Date(serverTime) : new Date();
  const reference = Number.isNaN(when.getTime()) ? new Date() : when;
  const hours =
    def && timeOptions
      ? sessionHoursLabel(def, timeOptions, reference)
      : session.hours || (def ? sessionHoursLabel(def) : "");

  if (session.status === "open") {
    if (session.closes_at) {
      return {
        name,
        hours,
        timingLabel: `Open until ${formatTimeOfDay(new Date(session.closes_at), timeOptions)}`,
      };
    }
    if (session.closes_at_label && !timeOptions) {
      return { name, hours, timingLabel: `Open until ${session.closes_at_label}` };
    }
    const closeAt = def ? currentSessionClose(def, reference) : null;
    if (closeAt) {
      return {
        name,
        hours,
        timingLabel: `Open until ${formatTimeOfDay(closeAt, timeOptions)}`,
      };
    }
  }

  if (session.next_open) {
    return {
      name,
      hours,
      timingLabel: `Next open ${formatTimeOfDay(new Date(session.next_open), timeOptions, true)}`,
    };
  }

  if (session.next_open_label && !timeOptions) {
    return { name, hours, timingLabel: `Next open ${session.next_open_label}` };
  }

  const nextOpen = def ? nextSessionOpen(def, reference) : null;
  if (nextOpen) {
    return {
      name,
      hours,
      timingLabel: `Next open ${formatTimeOfDay(nextOpen, timeOptions, true)}`,
    };
  }

  return { name, hours, timingLabel: null };
}

function buildLocalSessionStatuses(when: Date): MarketSessionStatus[] {
  const fxOpen = isForexOpen(when);
  return MARKET_SESSION_DEFS.map((def) => ({
    id: def.id,
    name: def.name,
    status: fxOpen && isSessionActive(def, when) ? "open" : "closed",
    hours: def.hours,
  }));
}

export function anyEnabledMarketOpen(
  sessions: MarketSessionStatus[],
  indicators: MarketIndicators,
  options?: { marketAvailable?: boolean; serverTime?: string },
): boolean {
  const hasEnabledIndicators = Object.values(indicators).some(Boolean);
  if (!hasEnabledIndicators) return true;

  const useLocalFallback = options?.marketAvailable === false || sessions.length === 0;
  const when = options?.serverTime ? new Date(options.serverTime) : new Date();
  const reference = Number.isNaN(when.getTime()) ? new Date() : when;
  const activeSessions = useLocalFallback ? buildLocalSessionStatuses(reference) : sessions;

  return activeSessions.some(
    (session) => isMarketIndicatorEnabled(indicators, session.id) && session.status === "open",
  );
}

export function anyEnabledTradingSessionOpen(
  sessions: MarketSessionStatus[],
  enabledSessions: ForexTradingSessions,
  options?: { marketAvailable?: boolean; serverTime?: string },
): boolean {
  if (!hasEnabledForexTradingSessions(enabledSessions)) return false;

  const useLocalFallback = options?.marketAvailable === false || sessions.length === 0;
  const when = options?.serverTime ? new Date(options.serverTime) : new Date();
  const reference = Number.isNaN(when.getTime()) ? new Date() : when;
  if (!isForexOpen(reference)) return false;

  const activeSessions = useLocalFallback ? buildLocalSessionStatuses(reference) : sessions;

  return activeSessions.some(
    (session) =>
      isForexTradingSessionEnabled(enabledSessions, session.id) && session.status === "open",
  );
}

export function isForexMarketOpen(
  _sessions: MarketSessionStatus[],
  options?: { marketAvailable?: boolean; serverTime?: string },
): boolean {
  const when = options?.serverTime ? new Date(options.serverTime) : new Date();
  const reference = Number.isNaN(when.getTime()) ? new Date() : when;
  return isForexOpen(reference);
}
