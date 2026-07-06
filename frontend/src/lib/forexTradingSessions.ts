import { MARKET_SESSION_DEFS } from "./marketSessionDefs";

export type ForexTradingSessions = Record<string, boolean>;

const APAC_SESSION_IDS = ["sydney", "asia"] as const;
const LEGACY_APAC_KEYS = ["tokyo", "singapore"] as const;

export const DEFAULT_FOREX_TRADING_SESSIONS: ForexTradingSessions = Object.fromEntries(
  MARKET_SESSION_DEFS.map((session) => [session.id, true]),
);

export const FOREX_TRADING_SESSIONS_UPDATED = "brokerai:forex-trading-sessions-updated";

export function notifyForexTradingSessionsUpdated(): void {
  window.dispatchEvent(new Event(FOREX_TRADING_SESSIONS_UPDATED));
}

function migrateLegacyApac(raw: ForexTradingSessions): ForexTradingSessions {
  const merged = { ...DEFAULT_FOREX_TRADING_SESSIONS };

  if ("asia" in raw) {
    const asiaEnabled = Boolean(raw.asia);
    for (const sessionId of APAC_SESSION_IDS) {
      if (!(sessionId in raw)) {
        merged[sessionId] = asiaEnabled;
      }
    }
  }

  if (!("asia" in raw)) {
    let legacyApac: boolean | null = null;
    for (const legacyKey of LEGACY_APAC_KEYS) {
      if (legacyKey in raw) {
        const enabled = Boolean(raw[legacyKey]);
        legacyApac = legacyApac === null ? enabled : legacyApac || enabled;
      }
    }
    if (legacyApac !== null) {
      merged.asia = legacyApac;
    }
  }

  return merged;
}

export function normalizeForexTradingSessions(
  raw: ForexTradingSessions | null | undefined,
): ForexTradingSessions {
  const normalized = { ...DEFAULT_FOREX_TRADING_SESSIONS };
  if (!raw) return normalized;

  const migrated = migrateLegacyApac(raw);
  for (const session of MARKET_SESSION_DEFS) {
    normalized[session.id] = Boolean(raw[session.id] ?? migrated[session.id]);
  }
  return normalized;
}

export function isForexTradingSessionEnabled(
  enabledSessions: ForexTradingSessions,
  sessionId: string,
): boolean {
  return Boolean(enabledSessions[sessionId]);
}

export function hasEnabledForexTradingSessions(
  enabledSessions: ForexTradingSessions,
): boolean {
  return Object.values(enabledSessions).some(Boolean);
}
