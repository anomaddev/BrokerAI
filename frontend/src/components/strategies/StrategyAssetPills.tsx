import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Plus, X } from "lucide-react";
import type { AssetClass } from "../../api/client";
import {
  ALL_ASSET_CLASSES,
  ASSET_CLASS_LABELS,
  MANUAL_SYMBOL_ASSET_CLASSES,
  loadInstrumentCatalog,
  normalizeInstrumentSymbol,
  specificSymbols,
  type StrategyInstrumentSelection,
} from "../../lib/strategies/instruments";

/** Compact labels for the builder nav pills. */
export const ASSET_PILL_LABELS: Record<AssetClass, string> = {
  forex: "Forex",
  metals: "Metals",
  stocks: "Stocks",
  crypto: "Crypto",
  futures: "Futures",
  options: "Options",
};

const CATALOG_ASSET_CLASSES: AssetClass[] = ["forex", "metals"];

type StrategyAssetPillsProps = {
  value: StrategyInstrumentSelection;
  onChange: (selection: StrategyInstrumentSelection) => void;
  supportedAssetClasses?: AssetClass[];
  /** ``single`` replaces the selection with one symbol (AI Strategies). */
  selectionMode?: "multi" | "single";
  /** Symbols claimed by another AI Strategy → owner name (shown disabled). */
  occupiedInstruments?: Record<string, string>;
};

function isCatalogClass(assetClass: AssetClass): boolean {
  return CATALOG_ASSET_CLASSES.includes(assetClass);
}

function classSelected(
  value: StrategyInstrumentSelection,
  assetClass: AssetClass,
): boolean {
  return specificSymbols(value[assetClass]).length > 0;
}

export default function StrategyAssetPills({
  value,
  onChange,
  supportedAssetClasses = ALL_ASSET_CLASSES,
  selectionMode = "multi",
  occupiedInstruments,
}: StrategyAssetPillsProps) {
  const singleMode = selectionMode === "single";
  const occupied = occupiedInstruments ?? {};
  const rootRef = useRef<HTMLDivElement>(null);
  const [openClass, setOpenClass] = useState<AssetClass | null>(null);
  const [catalogByClass, setCatalogByClass] = useState<Partial<Record<AssetClass, string[]>>>({});
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [searchDraft, setSearchDraft] = useState("");

  const enabledClasses = useMemo(
    () => new Set(supportedAssetClasses),
    [supportedAssetClasses],
  );

  useEffect(() => {
    let cancelled = false;
    setCatalogLoading(true);
    setCatalogError(null);
    // Always load catalogs for every asset type so disabled pills stay ready if enabled later.
    Promise.all(
      ALL_ASSET_CLASSES.map(async (assetClass) => ({
        assetClass,
        instruments: await loadInstrumentCatalog(assetClass),
      })),
    )
      .then((groups) => {
        if (cancelled) return;
        const next: Partial<Record<AssetClass, string[]>> = {};
        for (const group of groups) next[group.assetClass] = group.instruments;
        setCatalogByClass(next);
      })
      .catch((err) => {
        if (!cancelled) {
          setCatalogError(err instanceof Error ? err.message : "Failed to load instruments");
        }
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (openClass && !enabledClasses.has(openClass)) {
      setOpenClass(null);
    }
  }, [openClass, enabledClasses]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpenClass(null);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenClass(null);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  useEffect(() => {
    setSearchDraft("");
  }, [openClass]);

  function setClassSelection(assetClass: AssetClass, symbols: string[]) {
    const next = { ...value };
    if (symbols.length === 0) delete next[assetClass];
    else next[assetClass] = symbols;
    onChange(next);
  }

  function disableClass(assetClass: AssetClass) {
    setClassSelection(assetClass, []);
    if (openClass === assetClass) setOpenClass(null);
  }

  function togglePill(assetClass: AssetClass) {
    if (!enabledClasses.has(assetClass)) return;
    setOpenClass((current) => (current === assetClass ? null : assetClass));
  }

  function toggleSymbol(assetClass: AssetClass, symbol: string) {
    if (occupied[symbol] && !specificSymbols(value[assetClass]).includes(symbol)) {
      return;
    }
    const current = specificSymbols(value[assetClass]);
    if (singleMode) {
      if (current.includes(symbol)) {
        setClassSelection(assetClass, []);
      } else {
        // Single-instrument strategies clear other asset classes too.
        onChange({ [assetClass]: [symbol] } as StrategyInstrumentSelection);
      }
      return;
    }
    const next = current.includes(symbol)
      ? current.filter((item) => item !== symbol)
      : [...current, symbol];
    setClassSelection(assetClass, next);
  }

  function selectAll(assetClass: AssetClass) {
    if (singleMode) return;
    const catalog = catalogByClass[assetClass] ?? [];
    if (catalog.length === 0) return;
    setClassSelection(assetClass, [...catalog]);
  }

  function clearAll(assetClass: AssetClass) {
    setClassSelection(assetClass, []);
  }

  function addSearchSymbol(assetClass: AssetClass) {
    const symbol = normalizeInstrumentSymbol(assetClass, searchDraft);
    if (!symbol) return;
    const current = specificSymbols(value[assetClass]);
    if (!current.includes(symbol)) {
      setClassSelection(assetClass, [...current, symbol]);
    }
    setSearchDraft("");
  }

  const openSelected = openClass ? specificSymbols(value[openClass]) : [];
  const openCatalog = openClass ? (catalogByClass[openClass] ?? []) : [];
  const openIsCatalog = openClass ? isCatalogClass(openClass) : false;
  const openSupportsManual = openClass
    ? MANUAL_SYMBOL_ASSET_CLASSES.includes(openClass)
    : false;

  const searchResults = useMemo(() => {
    if (!openClass || openIsCatalog) return [];
    const query = searchDraft.trim().toUpperCase();
    const selected = new Set(openSelected);
    const fromCatalog = openCatalog.filter((symbol) => {
      if (selected.has(symbol)) return false;
      if (!query) return true;
      return symbol.includes(query);
    });
    return fromCatalog.slice(0, 40);
  }, [openClass, openIsCatalog, openCatalog, openSelected, searchDraft]);

  const canAddDraft =
    openClass &&
    openSupportsManual &&
    Boolean(normalizeInstrumentSymbol(openClass, searchDraft)) &&
    !openSelected.includes(normalizeInstrumentSymbol(openClass, searchDraft));

  return (
    <div className="strategy-asset-pills" ref={rootRef}>
      <div className="strategy-asset-pills-row" role="toolbar" aria-label="Asset types">
        {ALL_ASSET_CLASSES.map((assetClass) => {
          const enabled = enabledClasses.has(assetClass);
          const selected = enabled && classSelected(value, assetClass);
          const open = enabled && openClass === assetClass;
          const count = specificSymbols(value[assetClass]).length;
          return (
            <div key={assetClass} className="strategy-asset-pill-anchor">
              <div
                className={`strategy-asset-pill strategy-asset-pill--${assetClass}${
                  selected ? " strategy-asset-pill--selected" : ""
                }${open ? " strategy-asset-pill--open" : ""}${
                  enabled ? "" : " strategy-asset-pill--disabled"
                }`}
                title={enabled ? undefined : "Not available for this strategy template"}
              >
                <button
                  type="button"
                  className="strategy-asset-pill-toggle"
                  aria-pressed={selected}
                  aria-expanded={open}
                  aria-disabled={!enabled}
                  disabled={!enabled}
                  onClick={() => togglePill(assetClass)}
                >
                  <span>{ASSET_PILL_LABELS[assetClass]}</span>
                  {selected ? (
                    <span className="strategy-asset-pill-count">{count}</span>
                  ) : null}
                  {enabled ? (
                    <ChevronDown
                      size={12}
                      aria-hidden
                      className={`strategy-asset-pill-chevron${
                        open ? " strategy-asset-pill-chevron--open" : ""
                      }`}
                    />
                  ) : null}
                </button>
                {selected ? (
                  <button
                    type="button"
                    className="strategy-asset-pill-off"
                    aria-label={`Turn off ${ASSET_PILL_LABELS[assetClass]}`}
                    onClick={() => disableClass(assetClass)}
                  >
                    <X size={12} />
                  </button>
                ) : null}
              </div>

              {open ? (
                <div
                  className="strategy-asset-pill-dropdown"
                  role="dialog"
                  aria-label={`${ASSET_CLASS_LABELS[assetClass]} instruments`}
                >
                  <div className="strategy-asset-pill-dropdown-header">
                    <span className="strategy-asset-pill-dropdown-title">
                      {ASSET_CLASS_LABELS[assetClass]}
                    </span>
                    <button
                      type="button"
                      className="strategy-asset-pill-dropdown-disable"
                      onClick={() => disableClass(assetClass)}
                    >
                      Turn off
                    </button>
                  </div>

                  {catalogLoading ? (
                    <p className="settings-muted strategy-asset-pill-dropdown-status">
                      Loading instruments…
                    </p>
                  ) : null}
                  {catalogError && !catalogLoading ? (
                    <p className="settings-error strategy-asset-pill-dropdown-status">
                      {catalogError}
                    </p>
                  ) : null}

                  {openIsCatalog ? (
                    <>
                      {singleMode ? (
                        <p className="settings-muted strategy-asset-pill-dropdown-status">
                          Select exactly one instrument. Each pair can have only one AI Strategy.
                        </p>
                      ) : (
                        <div className="strategy-asset-pill-dropdown-toolbar">
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            disabled={
                              openCatalog.length === 0 ||
                              (openCatalog.length > 0 &&
                                openCatalog.every((symbol) => openSelected.includes(symbol)))
                            }
                            onClick={() => selectAll(assetClass)}
                          >
                            Select all
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            disabled={openSelected.length === 0}
                            onClick={() => clearAll(assetClass)}
                          >
                            Clear all
                          </button>
                        </div>
                      )}
                      {openCatalog.length === 0 && !catalogLoading ? (
                        <p className="settings-muted strategy-asset-pill-dropdown-status">
                          No instruments available.
                        </p>
                      ) : (
                        <div className="strategy-asset-pill-dropdown-grid">
                          {openCatalog.map((symbol) => {
                            const checked = openSelected.includes(symbol);
                            const owner = occupied[symbol];
                            const blocked = Boolean(owner) && !checked;
                            return (
                              <label
                                key={symbol}
                                className={`forex-pair-checkbox strategy-instrument-checkbox${
                                  checked ? " forex-pair-checkbox--checked" : ""
                                }${blocked ? " forex-pair-checkbox--disabled" : ""}`}
                                title={
                                  blocked
                                    ? `Already used by AI Strategy “${owner}”`
                                    : undefined
                                }
                              >
                                <input
                                  type={singleMode ? "radio" : "checkbox"}
                                  name={
                                    singleMode
                                      ? `strategy-instrument-${assetClass}`
                                      : undefined
                                  }
                                  className="ui-checkbox-input"
                                  checked={checked}
                                  disabled={blocked}
                                  onChange={() => toggleSymbol(assetClass, symbol)}
                                />
                                <span className="forex-pair-label">{symbol}</span>
                              </label>
                            );
                          })}
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <div className="strategy-asset-pill-search">
                        <input
                          type="text"
                          className="strategy-asset-pill-search-input"
                          placeholder={`Search or add ${ASSET_PILL_LABELS[assetClass].toLowerCase()} symbol…`}
                          value={searchDraft}
                          onChange={(event) => setSearchDraft(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault();
                              if (searchResults[0]) {
                                toggleSymbol(assetClass, searchResults[0]);
                                setSearchDraft("");
                              } else if (canAddDraft) {
                                addSearchSymbol(assetClass);
                              }
                            }
                          }}
                          autoFocus
                        />
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          disabled={!canAddDraft}
                          onClick={() => addSearchSymbol(assetClass)}
                        >
                          <Plus size={14} aria-hidden />
                          Add
                        </button>
                      </div>

                      {openSelected.length > 0 ? (
                        <div className="strategy-asset-pill-selected-list">
                          {openSelected.map((symbol) => (
                            <span key={symbol} className="strategy-asset-pill-chip">
                              {symbol}
                              <button
                                type="button"
                                className="strategy-asset-pill-chip-remove"
                                aria-label={`Remove ${symbol}`}
                                onClick={() => toggleSymbol(assetClass, symbol)}
                              >
                                <X size={12} />
                              </button>
                            </span>
                          ))}
                        </div>
                      ) : (
                        <p className="settings-muted strategy-asset-pill-dropdown-status">
                          Search the watchlist or type a symbol to add it.
                        </p>
                      )}

                      {searchResults.length > 0 ? (
                        <div className="strategy-asset-pill-search-results" role="listbox">
                          {searchResults.map((symbol) => (
                            <button
                              key={symbol}
                              type="button"
                              className="strategy-asset-pill-search-result"
                              role="option"
                              onClick={() => {
                                toggleSymbol(assetClass, symbol);
                                setSearchDraft("");
                              }}
                            >
                              {symbol}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
