import { MARKET_SESSION_DEFS } from "./marketSessionDefs";

export type MarketIndicators = Record<string, boolean>;

const APAC_SESSION_IDS = ["sydney", "asia"] as const;
const LEGACY_APAC_KEYS = ["tokyo", "singapore"] as const;

export const DEFAULT_MARKET_INDICATORS: MarketIndicators = Object.fromEntries(
  MARKET_SESSION_DEFS.map((session) => [session.id, true]),
);

export const DISPLAY_SETTINGS_UPDATED = "brokerai:display-settings-updated";

export function notifyDisplaySettingsUpdated(): void {
  window.dispatchEvent(new Event(DISPLAY_SETTINGS_UPDATED));
}

function migrateLegacyApac(raw: MarketIndicators): MarketIndicators {
  const merged = { ...DEFAULT_MARKET_INDICATORS };

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

export function normalizeMarketIndicators(raw: MarketIndicators | null | undefined): MarketIndicators {
  const normalized = { ...DEFAULT_MARKET_INDICATORS };
  if (!raw) return normalized;

  const migrated = migrateLegacyApac(raw);
  for (const session of MARKET_SESSION_DEFS) {
    normalized[session.id] = Boolean(raw[session.id] ?? migrated[session.id]);
  }
  return normalized;
}

export function isMarketIndicatorEnabled(
  indicators: MarketIndicators,
  sessionId: string,
): boolean {
  return indicators[sessionId] ?? true;
}
