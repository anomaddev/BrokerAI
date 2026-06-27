import { api, type AssetClass, type StrategyInstrumentSelection } from "../../api/client";
import type { StrategyTemplatePill } from "./types";

export type { StrategyInstrumentSelection };

export const ASSET_CLASS_LABELS: Record<AssetClass, string> = {
  forex: "Forex",
  metals: "Precious Metals",
  stocks: "Stocks",
  crypto: "Crypto",
  futures: "Futures",
  options: "Options",
};

export const ALL_ASSET_CLASSES: AssetClass[] = [
  "forex",
  "metals",
  "stocks",
  "crypto",
  "futures",
  "options",
];

/** Asset classes where users can type custom symbols in addition to catalog picks. */
export const MANUAL_SYMBOL_ASSET_CLASSES: AssetClass[] = [
  "stocks",
  "crypto",
  "futures",
  "options",
];

/** Sentinel stored in instrument_selection to mean "all watchlist symbols for this class". */
export const WATCHLIST_ALL_SYMBOL = "*";

export const WATCHLIST_ASSET_CLASSES: AssetClass[] = [...MANUAL_SYMBOL_ASSET_CLASSES];

export function supportsWatchlistAll(assetClass: AssetClass): boolean {
  return WATCHLIST_ASSET_CLASSES.includes(assetClass);
}

export function isWatchlistAllSelection(symbols: string[] | undefined): boolean {
  return symbols?.length === 1 && symbols[0] === WATCHLIST_ALL_SYMBOL;
}

export function specificSymbols(symbols: string[] | undefined): string[] {
  if (!symbols) return [];
  return symbols.filter((s) => s !== WATCHLIST_ALL_SYMBOL);
}

/** Static catalog for asset classes without a dedicated pairs API. */
export const METALS_SYMBOL_CATALOG = ["XAU/USD", "XAG/USD", "XPT/USD", "XPD/USD"];

export function emptyInstrumentSelection(): StrategyInstrumentSelection {
  return {};
}

export function countSelectedInstruments(selection: StrategyInstrumentSelection): number {
  return Object.values(selection).reduce((sum, symbols) => {
    if (!symbols?.length) return sum;
    if (isWatchlistAllSelection(symbols)) return sum + 1;
    return sum + specificSymbols(symbols).length;
  }, 0);
}

export function hasInstrumentSelection(selection: StrategyInstrumentSelection): boolean {
  return Object.values(selection).some((symbols) => symbols && symbols.length > 0);
}

export function instrumentSelectionSummary(
  selection: StrategyInstrumentSelection | undefined,
): string | null {
  if (!selection) return null;
  const parts: string[] = [];
  for (const assetClass of ALL_ASSET_CLASSES) {
    const symbols = selection[assetClass];
    if (!symbols?.length) continue;
    if (isWatchlistAllSelection(symbols)) {
      parts.push(`${ASSET_CLASS_LABELS[assetClass]} watchlist`);
      continue;
    }
    const specific = specificSymbols(symbols);
    if (specific.length === 1) {
      parts.push(specific[0]);
    } else if (specific.length > 1) {
      parts.push(`${specific.length} ${ASSET_CLASS_LABELS[assetClass].toLowerCase()}`);
    }
  }
  return parts.length > 0 ? parts.join(", ") : null;
}

export function normalizeInstrumentSymbol(assetClass: AssetClass, raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "";
  if (assetClass === "forex" || assetClass === "metals") {
    return trimmed.toUpperCase();
  }
  return trimmed.toUpperCase();
}

export type StrategyAssignmentMode = "asset_class" | "specific";

export type StrategyAssignment = {
  enabled: boolean;
  assignmentMode: StrategyAssignmentMode;
  assetClass: AssetClass;
  selectedInstruments: string[];
};

export const DEFAULT_STRATEGY_ASSIGNMENT: StrategyAssignment = {
  enabled: false,
  assignmentMode: "asset_class",
  assetClass: "forex",
  selectedInstruments: [],
};

export async function loadInstrumentCatalog(assetClass: AssetClass): Promise<string[]> {
  if (assetClass === "forex") {
    const data = await api.getForexPairs();
    return data.pair_order?.length ? [...data.pair_order] : [...data.catalog].sort((a, b) => a.localeCompare(b));
  }
  if (assetClass === "metals") {
    return [...METALS_SYMBOL_CATALOG];
  }
  const data = await api.getAssetSettings(assetClass);
  const symbols = data.enabled_symbols ?? data.enabled_pairs ?? [];
  return [...symbols].sort((a, b) => a.localeCompare(b));
}

export function assignmentSummary(assignment: StrategyAssignment): string {
  if (!assignment.enabled) return "Disabled";
  if (assignment.assignmentMode === "asset_class") {
    return ASSET_CLASS_LABELS[assignment.assetClass];
  }
  const count = assignment.selectedInstruments.length;
  if (count === 0) return "No instruments selected";
  if (count === 1) return assignment.selectedInstruments[0];
  return `${count} assets`;
}

export type TemplateAssetSuggestions = {
  wholeAssetClasses: Set<AssetClass>;
  symbolsByClass: Map<AssetClass, Set<string>>;
};

/** Resolve template pills into asset-class-wide and per-symbol suggestions. */
export function buildTemplateAssetSuggestions(
  pills: StrategyTemplatePill[],
): TemplateAssetSuggestions {
  const wholeAssetClasses = new Set<AssetClass>();
  const symbolsByClass = new Map<AssetClass, Set<string>>();

  for (const pill of pills) {
    const classLabel = ASSET_CLASS_LABELS[pill.assetClass];
    if (pill.label === classLabel) {
      wholeAssetClasses.add(pill.assetClass);
      continue;
    }
    const normalized = normalizeInstrumentSymbol(pill.assetClass, pill.label);
    if (!normalized) continue;
    const existing = symbolsByClass.get(pill.assetClass) ?? new Set<string>();
    existing.add(normalized);
    symbolsByClass.set(pill.assetClass, existing);
  }

  return { wholeAssetClasses, symbolsByClass };
}

/** True when the template explicitly names this symbol in its pills. */
export function isTemplateSuggestedSymbol(
  assetClass: AssetClass,
  symbol: string,
  suggestions: TemplateAssetSuggestions,
): boolean {
  const normalized = normalizeInstrumentSymbol(assetClass, symbol);
  return suggestions.symbolsByClass.get(assetClass)?.has(normalized) ?? false;
}

/** True when the template tags the whole asset class (parent-level suggestion). */
export function isTemplateSuggestedAssetClass(
  assetClass: AssetClass,
  suggestions: TemplateAssetSuggestions,
): boolean {
  return suggestions.wholeAssetClasses.has(assetClass);
}
