import { MARKET_SESSION_DEFS } from "./marketSessionDefs";

export type MarketIndicators = Record<string, boolean>;

export const DEFAULT_MARKET_INDICATORS: MarketIndicators = Object.fromEntries(
  MARKET_SESSION_DEFS.map((session) => [session.id, true]),
);

export const DISPLAY_SETTINGS_UPDATED = "brokerai:display-settings-updated";

export function notifyDisplaySettingsUpdated(): void {
  window.dispatchEvent(new Event(DISPLAY_SETTINGS_UPDATED));
}

export function normalizeMarketIndicators(raw: MarketIndicators | null | undefined): MarketIndicators {
  const normalized = { ...DEFAULT_MARKET_INDICATORS };
  if (!raw) return normalized;
  for (const session of MARKET_SESSION_DEFS) {
    if (session.id in raw) {
      normalized[session.id] = Boolean(raw[session.id]);
    }
  }
  return normalized;
}

export function isMarketIndicatorEnabled(
  indicators: MarketIndicators,
  sessionId: string,
): boolean {
  return indicators[sessionId] ?? true;
}
