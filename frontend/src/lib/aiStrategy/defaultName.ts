import { clampStrategyTitle } from "../strategyBuilder/components";
import {
  instrumentSelectionSummary,
  type StrategyInstrumentSelection,
} from "../strategies/instruments";

/** Canonical create-time name: `AI Strategy - {symbol}`. */
export function defaultAiStrategyName(symbol: string): string {
  const pair = symbol.trim();
  if (!pair) return clampStrategyTitle("AI Strategy");
  return clampStrategyTitle(`AI Strategy - ${pair}`);
}

export function selectedAiStrategySymbol(
  selection: StrategyInstrumentSelection | undefined,
): string | null {
  return instrumentSelectionSummary(selection);
}

/** True when the title is still the auto-generated / placeholder form. */
export function isAutoAiStrategyTitle(title: string, symbol?: string | null): boolean {
  const trimmed = title.trim();
  if (!trimmed || trimmed === "AI Strategy") return true;
  if (symbol && trimmed === defaultAiStrategyName(symbol)) return true;
  return /^AI Strategy - .+$/.test(trimmed);
}
