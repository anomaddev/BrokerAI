import type { MarketSessionStatus } from "../api/client";
import { formatAppTimeOfDay, formatSessionHours, type TimeFormatOptions } from "./formatTime";
import { isMarketIndicatorEnabled, type MarketIndicators } from "./displaySettings";
import {
  MARKET_SESSION_DEFS,
  SESSION_BY_ID,
  type SessionDef,
} from "./marketSessionDefs";

export { MARKET_SESSION_DEFS, type SessionDef } from "./marketSessionDefs";

function minutesSinceMidnight(date: Date): number {
  return date.getUTCHours() * 60 + date.getUTCMinutes();
}

export function isForexHours(date: Date): boolean {
  const weekday = date.getUTCDay();
  const minutes = minutesSinceMidnight(date);

  if (weekday === 6) return false;
  if (weekday === 0 && minutes < 22 * 60) return false;
  if (weekday === 5 && minutes >= 22 * 60) return false;
  return true;
}

function isSessionActive(def: SessionDef, date: Date): boolean {
  const minutes = minutesSinceMidnight(date);
  const start = def.startHour * 60 + def.startMinute;
  const end = def.endHour * 60 + def.endMinute;
  return start <= minutes && minutes < end;
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

function sessionOpenAt(def: SessionDef, date: Date): Date {
  return new Date(
    Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), def.startHour, def.startMinute),
  );
}

function sessionCloseAt(def: SessionDef, date: Date): Date {
  return new Date(
    Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), def.endHour, def.endMinute),
  );
}

function nextSessionOpen(def: SessionDef, from: Date): Date | null {
  for (let dayOffset = 0; dayOffset < 8; dayOffset += 1) {
    const day = new Date(from);
    day.setUTCDate(day.getUTCDate() + dayOffset);
    const openAt = sessionOpenAt(def, day);
    if (openAt <= from) continue;
    if (!isForexHours(openAt)) continue;
    return openAt;
  }
  return null;
}

function previousSessionClose(def: SessionDef, before: Date): Date | null {
  for (let dayOffset = 0; dayOffset < 8; dayOffset += 1) {
    const day = new Date(before);
    day.setUTCDate(day.getUTCDate() - dayOffset);
    const closeAt = sessionCloseAt(def, day);
    if (closeAt < before && isForexHours(closeAt)) {
      return closeAt;
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

export function findEarliestNextMarketOpen(
  sessions: MarketSessionStatus[],
  indicators: MarketIndicators,
  now: Date,
  options?: { marketAvailable?: boolean; serverTime?: string },
): MarketOpenTarget | null {
  const hasEnabledIndicators = Object.values(indicators).some(Boolean);
  if (!hasEnabledIndicators) return null;

  const useLocalFallback = options?.marketAvailable === false || sessions.length === 0;
  const when = options?.serverTime ? new Date(options.serverTime) : now;
  const reference = Number.isNaN(when.getTime()) ? now : when;
  const activeSessions = useLocalFallback ? buildLocalSessionStatuses(reference) : sessions;

  let earliest: MarketOpenTarget | null = null;

  for (const session of activeSessions) {
    if (!isMarketIndicatorEnabled(indicators, session.id)) continue;
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
  if (!isSessionActive(def, from) || !isForexHours(from)) return null;
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
      : session.hours || def?.hours || "";

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
  const fxOpen = isForexHours(when);
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
