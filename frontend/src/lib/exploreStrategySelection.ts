import type { Strategy } from "../api/client";
import { isWatchlistAllSelection, specificSymbols } from "./strategies/instruments";

export function strategyCoversSymbol(strategy: Strategy, symbol: string | null): boolean {
  if (!symbol) return true;

  const normalized = symbol.toUpperCase();
  if (strategy.instruments.some((item) => item.toUpperCase() === normalized)) {
    return true;
  }

  const selection = strategy.instrument_selection;
  if (!selection) return false;

  for (const symbols of Object.values(selection)) {
    if (!symbols?.length) continue;
    if (isWatchlistAllSelection(symbols)) return true;
    if (specificSymbols(symbols).some((item) => item.toUpperCase() === normalized)) {
      return true;
    }
  }

  return false;
}

export function filterEnabledStrategies(strategies: Strategy[]): Strategy[] {
  return strategies.filter((strategy) => strategy.enabled);
}

export function sortStrategiesForExplore(
  strategies: Strategy[],
  symbol: string | null,
): Strategy[] {
  return [...strategies].sort((a, b) => {
    const aCovers = strategyCoversSymbol(a, symbol);
    const bCovers = strategyCoversSymbol(b, symbol);
    if (aCovers !== bCovers) return aCovers ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}
