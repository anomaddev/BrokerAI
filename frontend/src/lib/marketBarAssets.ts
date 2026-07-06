import {
  DEFAULT_FOREX_TRADING_SESSIONS,
  isForexTradingSessionEnabled,
  type ForexTradingSessions,
} from "./forexTradingSessions";
import { METALS_SYMBOL_CATALOG } from "./strategies/instruments";

export type MarketBarAssetContext = {
  forexEnabled: boolean;
  hasForexPairs: boolean;
  enabledSessions: ForexTradingSessions;
  metalsEnabled: boolean;
  hasMetalsSymbols: boolean;
};

export const EMPTY_MARKET_BAR_ASSET_CONTEXT: MarketBarAssetContext = {
  forexEnabled: false,
  hasForexPairs: false,
  enabledSessions: DEFAULT_FOREX_TRADING_SESSIONS,
  metalsEnabled: false,
  hasMetalsSymbols: false,
};

/** Asset classes configured and open on the FX calendar. */
export function openAssetClasses(context: MarketBarAssetContext): string[] {
  const assetClasses: string[] = [];

  if (context.forexEnabled && context.hasForexPairs) {
    assetClasses.push("Forex");
  }

  if (context.metalsEnabled && context.hasMetalsSymbols) {
    assetClasses.push("Metals");
  }

  return assetClasses;
}

/** Asset classes actively trading during an open liquidity session pill. */
export function assetClassesForOpenSession(
  sessionId: string,
  context: MarketBarAssetContext,
): string[] {
  const assetClasses: string[] = [];

  if (
    context.forexEnabled &&
    context.hasForexPairs &&
    isForexTradingSessionEnabled(context.enabledSessions, sessionId)
  ) {
    assetClasses.push("Forex");
  }

  if (context.metalsEnabled && context.hasMetalsSymbols) {
    assetClasses.push("Metals");
  }

  return assetClasses;
}

export function hasConfiguredMetalsSymbols(raw: string[] | undefined): boolean {
  return (raw ?? []).some((symbol) => METALS_SYMBOL_CATALOG.includes(symbol));
}
