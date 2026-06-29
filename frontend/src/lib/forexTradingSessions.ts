import { MARKET_SESSION_DEFS } from "./marketSessionDefs";

export type ForexTradingSessions = Record<string, boolean>;

export const DEFAULT_FOREX_TRADING_SESSIONS: ForexTradingSessions = Object.fromEntries(
  MARKET_SESSION_DEFS.map((session) => [session.id, true]),
);

export function normalizeForexTradingSessions(
  raw: ForexTradingSessions | null | undefined,
): ForexTradingSessions {
  const normalized = { ...DEFAULT_FOREX_TRADING_SESSIONS };
  if (!raw) return normalized;
  for (const session of MARKET_SESSION_DEFS) {
    if (session.id in raw) {
      normalized[session.id] = Boolean(raw[session.id]);
    }
  }
  return normalized;
}
