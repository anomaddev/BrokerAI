import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Folder } from "lucide-react";
import type { AssetClass } from "../../api/client";
import {
  ALL_ASSET_CLASSES,
  ASSET_CLASS_LABELS,
  buildTemplateAssetSuggestions,
  countSelectedInstruments,
  isTemplateSuggestedAssetClass,
  isTemplateSuggestedSymbol,
  isWatchlistAllSelection,
  loadInstrumentCatalog,
  MANUAL_SYMBOL_ASSET_CLASSES,
  normalizeInstrumentSymbol,
  specificSymbols,
  supportsWatchlistAll,
  WATCHLIST_ALL_SYMBOL,
  type StrategyInstrumentSelection,
} from "../../lib/strategies/instruments";
import type { StrategyTemplatePill } from "../../lib/strategies/types";

type CatalogGroup = {
  assetClass: AssetClass;
  instruments: string[];
};

type StrategyAssetTreePickerProps = {
  value: StrategyInstrumentSelection;
  onChange: (selection: StrategyInstrumentSelection) => void;
  supportedAssetClasses?: AssetClass[];
  /** Pills from the selected template — matching assets show a "Suggested" tag. */
  suggestedPills?: StrategyTemplatePill[];
};

function mergeCatalogAndSelection(catalog: string[], selected: string[]): string[] {
  const seen = new Set<string>();
  const merged: string[] = [];
  for (const symbol of [...catalog, ...specificSymbols(selected)]) {
    if (!seen.has(symbol)) {
      seen.add(symbol);
      merged.push(symbol);
    }
  }
  return merged;
}

export default function StrategyAssetTreePicker({
  value,
  onChange,
  supportedAssetClasses = ALL_ASSET_CLASSES,
  suggestedPills = [],
}: StrategyAssetTreePickerProps) {
  const [catalogGroups, setCatalogGroups] = useState<CatalogGroup[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<AssetClass>>(
    () => new Set(supportedAssetClasses.slice(0, 1)),
  );
  const [manualInputs, setManualInputs] = useState<Partial<Record<AssetClass, string>>>({});
  const folderCheckboxRefs = useRef<Partial<Record<AssetClass, HTMLInputElement | null>>>({});

  useEffect(() => {
    let cancelled = false;
    setCatalogLoading(true);
    setCatalogError(null);
    Promise.all(
      supportedAssetClasses.map(async (assetClass) => ({
        assetClass,
        instruments: await loadInstrumentCatalog(assetClass),
      })),
    )
      .then((groups) => {
        if (!cancelled) setCatalogGroups(groups);
      })
      .catch((err) => {
        if (!cancelled) {
          setCatalogError(err instanceof Error ? err.message : "Failed to load instruments");
          setCatalogGroups([]);
        }
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [supportedAssetClasses]);

  const catalogByClass = useMemo(() => {
    const map = new Map<AssetClass, string[]>();
    for (const group of catalogGroups) {
      map.set(group.assetClass, group.instruments);
    }
    return map;
  }, [catalogGroups]);

  const templateSuggestions = useMemo(
    () => buildTemplateAssetSuggestions(suggestedPills),
    [suggestedPills],
  );

  useEffect(() => {
    for (const assetClass of supportedAssetClasses) {
      const checkbox = folderCheckboxRefs.current[assetClass];
      if (!checkbox) continue;
      const catalog = catalogByClass.get(assetClass) ?? [];
      const selected = value[assetClass] ?? [];
      const watchlistAll = isWatchlistAllSelection(selected);
      const specific = specificSymbols(selected);
      const symbols = mergeCatalogAndSelection(catalog, specific);
      const allSpecificSelected =
        symbols.length > 0 && symbols.every((symbol) => specific.includes(symbol));
      const allSelected = watchlistAll || allSpecificSelected;
      const someSelected = watchlistAll || specific.length > 0;
      checkbox.indeterminate = someSelected && !allSelected;
      checkbox.checked = allSelected;
    }
  }, [value, catalogByClass, supportedAssetClasses]);

  function toggleFolder(assetClass: AssetClass) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(assetClass)) next.delete(assetClass);
      else next.add(assetClass);
      return next;
    });
  }

  function setClassSelection(assetClass: AssetClass, symbols: string[]) {
    const next = { ...value };
    if (symbols.length === 0) {
      delete next[assetClass];
    } else {
      next[assetClass] = symbols;
    }
    onChange(next);
  }

  function setWatchlistAll(assetClass: AssetClass, enabled: boolean) {
    if (enabled) {
      setClassSelection(assetClass, [WATCHLIST_ALL_SYMBOL]);
    } else {
      setClassSelection(assetClass, []);
    }
  }

  function toggleSymbol(assetClass: AssetClass, symbol: string) {
    const current = specificSymbols(value[assetClass]);
    const nextSymbols = current.includes(symbol)
      ? current.filter((s) => s !== symbol)
      : [...current, symbol];
    setClassSelection(assetClass, nextSymbols);
  }

  function selectAllInClass(assetClass: AssetClass) {
    const catalog = catalogByClass.get(assetClass) ?? [];
    const current = specificSymbols(value[assetClass]);
    const merged = mergeCatalogAndSelection(catalog, current);
    if (merged.length === 0 && supportsWatchlistAll(assetClass)) {
      setWatchlistAll(assetClass, true);
      return;
    }
    setClassSelection(assetClass, merged);
  }

  function deselectAllInClass(assetClass: AssetClass) {
    setClassSelection(assetClass, []);
  }

  function toggleFolderCheckbox(assetClass: AssetClass) {
    const catalog = catalogByClass.get(assetClass) ?? [];
    const selected = value[assetClass] ?? [];
    const watchlistAll = isWatchlistAllSelection(selected);
    const specific = specificSymbols(selected);
    const symbols = mergeCatalogAndSelection(catalog, specific);

    if (symbols.length === 0 && supportsWatchlistAll(assetClass)) {
      setWatchlistAll(assetClass, !watchlistAll);
      return;
    }

    const allSpecificSelected =
      symbols.length > 0 && symbols.every((symbol) => specific.includes(symbol));
    if (watchlistAll || allSpecificSelected) {
      deselectAllInClass(assetClass);
    } else if (symbols.length > 0) {
      setClassSelection(assetClass, symbols);
    } else if (supportsWatchlistAll(assetClass)) {
      setWatchlistAll(assetClass, true);
    }
  }

  function addManualSymbol(assetClass: AssetClass) {
    const raw = manualInputs[assetClass] ?? "";
    const symbol = normalizeInstrumentSymbol(assetClass, raw);
    if (!symbol) return;
    const current = specificSymbols(value[assetClass]);
    if (current.includes(symbol)) {
      setManualInputs((prev) => ({ ...prev, [assetClass]: "" }));
      return;
    }
    setClassSelection(assetClass, [...current, symbol]);
    setManualInputs((prev) => ({ ...prev, [assetClass]: "" }));
  }

  const totalSelected = countSelectedInstruments(value);

  return (
    <div className="strategy-asset-tree">
      <div className="strategy-asset-tree-header">
        <span className="param-control-label">Enabled assets</span>
        <span className="strategy-asset-tree-summary">
          {totalSelected > 0 ? `${totalSelected} selected` : "None selected"}
        </span>
      </div>

      {catalogLoading && (
        <p className="settings-muted strategy-instrument-picker-status">Loading instruments…</p>
      )}
      {catalogError && !catalogLoading && (
        <p className="settings-error strategy-instrument-picker-status">{catalogError}</p>
      )}

      {!catalogLoading &&
        supportedAssetClasses.map((assetClass) => {
          const catalog = catalogByClass.get(assetClass) ?? [];
          const selected = value[assetClass] ?? [];
          const watchlistAll = isWatchlistAllSelection(selected);
          const specific = specificSymbols(selected);
          const symbols = mergeCatalogAndSelection(catalog, specific);
          const isExpanded = expanded.has(assetClass);
          const supportsManual = MANUAL_SYMBOL_ASSET_CLASSES.includes(assetClass);
          const supportsWatchlist = supportsWatchlistAll(assetClass);
          const allSpecificSelected =
            symbols.length > 0 && symbols.every((symbol) => specific.includes(symbol));
          const allSelected = watchlistAll || allSpecificSelected;
          const noneSelected = !watchlistAll && specific.length === 0;
          const isClassSuggested = isTemplateSuggestedAssetClass(assetClass, templateSuggestions);

          return (
            <div
              key={assetClass}
              className={`strategy-asset-folder${isExpanded ? " strategy-asset-folder--expanded" : ""}${
                isClassSuggested ? " strategy-asset-folder--suggested" : ""
              }`}
            >
              <div className="strategy-asset-folder-header">
                <button
                  type="button"
                  className="strategy-asset-folder-toggle"
                  onClick={() => toggleFolder(assetClass)}
                  aria-expanded={isExpanded}
                  aria-label={`${isExpanded ? "Collapse" : "Expand"} ${ASSET_CLASS_LABELS[assetClass]}`}
                >
                  <ChevronDown className="strategy-asset-folder-chevron" aria-hidden="true" size={16} />
                </button>
                <label className="strategy-asset-folder-checkbox">
                  <input
                    ref={(el) => {
                      folderCheckboxRefs.current[assetClass] = el;
                    }}
                    type="checkbox"
                    className="ui-checkbox-input"
                    onChange={() => toggleFolderCheckbox(assetClass)}
                  />
                </label>
                <button
                  type="button"
                  className="strategy-asset-folder-label"
                  onClick={() => toggleFolder(assetClass)}
                >
                  <Folder size={15} aria-hidden="true" className="strategy-asset-folder-icon" />
                  <span>{ASSET_CLASS_LABELS[assetClass]}</span>
                  {isClassSuggested && (
                    <span className="strategy-asset-suggested-tag">Suggested</span>
                  )}
                  {watchlistAll ? (
                    <span className="strategy-asset-folder-count strategy-asset-folder-count--watchlist">
                      All watchlist
                    </span>
                  ) : specific.length > 0 ? (
                    <span className="strategy-asset-folder-count">{specific.length}</span>
                  ) : null}
                </button>
              </div>

              {isExpanded && (
                <div className="strategy-asset-folder-body">
                  {supportsWatchlist && (
                    <label
                      className={`strategy-watchlist-all-option${
                        watchlistAll ? " strategy-watchlist-all-option--checked" : ""
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="ui-checkbox-input"
                        checked={watchlistAll}
                        onChange={(e) => setWatchlistAll(assetClass, e.target.checked)}
                      />
                      <span className="strategy-watchlist-all-option-text">
                        <span className="strategy-watchlist-all-option-label">
                          Entire {ASSET_CLASS_LABELS[assetClass].toLowerCase()} watchlist
                        </span>
                        <span className="strategy-watchlist-all-option-hint">
                          Run on all symbols in your watchlist — including ones you add later in
                          Settings.
                        </span>
                      </span>
                    </label>
                  )}

                  {symbols.length > 0 && (
                    <div className="strategy-asset-folder-toolbar">
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        disabled={allSelected}
                        onClick={() => selectAllInClass(assetClass)}
                      >
                        Select all
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        disabled={noneSelected}
                        onClick={() => deselectAllInClass(assetClass)}
                      >
                        Clear
                      </button>
                    </div>
                  )}

                  {supportsManual && (
                    <div className="strategy-asset-manual-entry">
                      <input
                        type="text"
                        className="strategy-asset-manual-input"
                        placeholder={`Add ${ASSET_CLASS_LABELS[assetClass].toLowerCase()} symbol…`}
                        value={manualInputs[assetClass] ?? ""}
                        onChange={(e) =>
                          setManualInputs((prev) => ({
                            ...prev,
                            [assetClass]: e.target.value,
                          }))
                        }
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            addManualSymbol(assetClass);
                          }
                        }}
                      />
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => addManualSymbol(assetClass)}
                      >
                        Add
                      </button>
                    </div>
                  )}

                  {watchlistAll && symbols.length === 0 ? (
                    <p className="settings-muted strategy-asset-folder-empty">
                      No individual symbols selected — the strategy will follow your{" "}
                      {ASSET_CLASS_LABELS[assetClass].toLowerCase()} watchlist.
                    </p>
                  ) : symbols.length === 0 ? (
                    <p className="settings-muted strategy-asset-folder-empty">
                      {supportsWatchlist
                        ? "Select the entire watchlist above, or add individual symbols."
                        : "No instruments available. Configure this asset class in Settings first."}
                    </p>
                  ) : (
                    <div className="strategy-instrument-grid strategy-asset-folder-grid">
                      {symbols.map((symbol) => {
                        const checked = specific.includes(symbol);
                        const isManualOnly = !catalog.includes(symbol);
                        const isSuggested = isTemplateSuggestedSymbol(
                          assetClass,
                          symbol,
                          templateSuggestions,
                        );
                        return (
                          <label
                            key={symbol}
                            className={`forex-pair-checkbox strategy-instrument-checkbox${
                              checked ? " forex-pair-checkbox--checked" : ""
                            }${isManualOnly ? " strategy-instrument-checkbox--manual" : ""}${
                              isSuggested ? " strategy-instrument-checkbox--suggested" : ""
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="ui-checkbox-input"
                              checked={checked}
                              onChange={() => toggleSymbol(assetClass, symbol)}
                            />
                            <span className="forex-pair-label">{symbol}</span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

      {totalSelected === 0 && !catalogLoading && !catalogError && (
        <p className="param-helper param-helper--warn">
          Select at least one asset to enable this strategy.
        </p>
      )}
    </div>
  );
}
