import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Strategy } from "../../api/client";
import {
  appendOverlayItems,
  createStandaloneIndicator,
  decomposeStrategyToLayers,
  strategyAlreadyOnChart,
  type ChartOverlayItem,
} from "../../lib/chart/chartOverlayState";
import {
  INDICATOR_CATALOG,
  type IndicatorCatalogType,
} from "../../lib/chart/indicatorCatalog";
import {
  filterEnabledStrategies,
  sortStrategiesForExplore,
  strategyCoversSymbol,
} from "../../lib/exploreStrategySelection";
import { TIMEFRAME_LABELS, type Timeframe } from "../../lib/strategyParams";

type OverlaySearchAutocompleteProps = {
  symbol: string | null;
  chartTimeframe: Timeframe;
  overlayItems: ChartOverlayItem[];
  onOverlayItemsChange: (items: ChartOverlayItem[]) => void;
};

type AutocompleteOption =
  | { kind: "indicator"; type: IndicatorCatalogType; label: string; description: string }
  | { kind: "strategy"; strategy: Strategy; label: string; description: string };

type OptionGroup = {
  id: string;
  label: string;
  options: AutocompleteOption[];
};

function strategyTimeframe(strategy: Strategy): Timeframe | null {
  return strategy.timeframe ?? strategy.params?.timeframe ?? null;
}

function matchesQuery(text: string, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return text.toLowerCase().includes(normalized);
}

export default function OverlaySearchAutocomplete({
  symbol,
  chartTimeframe,
  overlayItems,
  onOverlayItemsChange,
}: OverlaySearchAutocompleteProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    api
      .listStrategies()
      .then((data) => {
        if (cancelled) return;
        setStrategies(filterEnabledStrategies(data.strategies));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load strategies");
        setStrategies([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const sortedStrategies = useMemo(
    () => sortStrategiesForExplore(strategies, symbol),
    [strategies, symbol],
  );

  const availableStrategies = useMemo(
    () => sortedStrategies.filter((strategy) => !strategyAlreadyOnChart(overlayItems, strategy.id)),
    [sortedStrategies, overlayItems],
  );

  const groups = useMemo((): OptionGroup[] => {
    const indicatorOptions: AutocompleteOption[] = INDICATOR_CATALOG.filter(
      (entry) =>
        matchesQuery(entry.label, query) || matchesQuery(entry.description, query),
    ).map((entry) => ({
      kind: "indicator" as const,
      type: entry.type,
      label: entry.label,
      description: entry.description,
    }));

    const strategyOptions: AutocompleteOption[] = availableStrategies.filter((strategy) => {
      const timeframe = strategyTimeframe(strategy);
      const suffix = [
        timeframe ? TIMEFRAME_LABELS[timeframe] : null,
        symbol && !strategyCoversSymbol(strategy, symbol) ? "other pairs" : null,
      ]
        .filter(Boolean)
        .join(" · ");
      const label = suffix ? `${strategy.name} (${suffix})` : strategy.name;
      return matchesQuery(strategy.name, query) || matchesQuery(label, query);
    }).map((strategy) => {
      const timeframe = strategyTimeframe(strategy);
      const suffix = [
        timeframe ? TIMEFRAME_LABELS[timeframe] : null,
        symbol && !strategyCoversSymbol(strategy, symbol) ? "other pairs" : null,
      ]
        .filter(Boolean)
        .join(" · ");
      return {
        kind: "strategy" as const,
        strategy,
        label: strategy.name,
        description: suffix || "Enabled strategy",
      };
    });

    const result: OptionGroup[] = [];
    if (indicatorOptions.length > 0) {
      result.push({ id: "indicators", label: "Indicators", options: indicatorOptions });
    }
    if (strategyOptions.length > 0) {
      result.push({ id: "strategies", label: "Strategies", options: strategyOptions });
    }
    return result;
  }, [query, availableStrategies, symbol]);

  const flatOptions = useMemo(
    () => groups.flatMap((group) => group.options),
    [groups],
  );

  const indexedGroups = useMemo(
    () => {
      let index = 0;
      return groups.map((group) => ({
        ...group,
        options: group.options.map((option) => {
          const currentIndex = index;
          index += 1;
          return { option, index: currentIndex };
        }),
      }));
    },
    [groups],
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [query, flatOptions.length]);

  useEffect(() => {
    if (!open) return;

    function handleClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  function selectOption(option: AutocompleteOption) {
    if (option.kind === "indicator") {
      onOverlayItemsChange(appendOverlayItems(overlayItems, [createStandaloneIndicator(option.type)]));
    } else {
      onOverlayItemsChange(
        appendOverlayItems(overlayItems, decomposeStrategyToLayers(option.strategy)),
      );
    }
    setQuery("");
    setOpen(false);
    inputRef.current?.focus();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((prev) => Math.min(prev + 1, Math.max(flatOptions.length - 1, 0)));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((prev) => Math.max(prev - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const match = flatOptions[activeIndex];
      if (match) selectOption(match);
      return;
    }
    if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const strategyWarnings = useMemo(() => {
    const strategyIds = new Set<string>();
    for (const item of overlayItems) {
      if (item.source.kind === "strategy") {
        strategyIds.add(item.source.strategyId);
      }
    }

    const notes: { strategy: Strategy; timeframeMismatch: boolean; symbolMismatch: boolean }[] = [];
    for (const strategyId of strategyIds) {
      const strategy = sortedStrategies.find((entry) => entry.id === strategyId);
      if (!strategy) continue;
      const timeframe = strategyTimeframe(strategy);
      notes.push({
        strategy,
        timeframeMismatch: timeframe != null && timeframe !== chartTimeframe,
        symbolMismatch: Boolean(symbol && !strategyCoversSymbol(strategy, symbol)),
      });
    }
    return notes;
  }, [overlayItems, sortedStrategies, chartTimeframe, symbol]);

  return (
    <div className="explore-overlay-search-wrap">
      <div className="explore-search explore-overlay-search" ref={rootRef}>
        <input
          ref={inputRef}
          type="search"
          className="research-search explore-search-input"
          placeholder={loading ? "Loading overlays…" : "Add indicator or strategy…"}
          value={query}
          aria-label="Add chart overlay"
          aria-autocomplete="list"
          aria-expanded={open && flatOptions.length > 0}
          aria-controls="explore-overlay-suggestions"
          role="combobox"
          disabled={loading}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onKeyDown={handleKeyDown}
        />
        {open && flatOptions.length > 0 ? (
          <div
            id="explore-overlay-suggestions"
            className="explore-search-dropdown explore-overlay-autocomplete"
            role="listbox"
            aria-label="Overlay suggestions"
          >
            {indexedGroups.map((group) => (
              <div key={group.id} className="explore-overlay-autocomplete-group">
                <div className="explore-overlay-autocomplete-group-label">{group.label}</div>
                <ul className="explore-overlay-autocomplete-options">
                  {group.options.map(({ option, index }) => (
                    <li key={option.kind === "indicator" ? option.type : option.strategy.id}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={index === activeIndex}
                        className={`explore-search-option${
                          index === activeIndex ? " explore-search-option--active" : ""
                        }`}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => selectOption(option)}
                        onMouseEnter={() => setActiveIndex(index)}
                      >
                        <span className="explore-overlay-option-label">{option.label}</span>
                        <span className="explore-overlay-option-desc">{option.description}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      {error ? (
        <p className="explore-sidebar-status explore-sidebar-status--error">{error}</p>
      ) : null}

      {!loading && strategies.length === 0 && !error ? (
        <p className="explore-strategy-note">
          No enabled strategies.{" "}
          <Link to="/strategies" className="explore-sidebar-link">
            Manage strategies
          </Link>
        </p>
      ) : null}

      {strategyWarnings.map(({ strategy, timeframeMismatch, symbolMismatch }) => (
        <div key={strategy.id} className="explore-strategy-meta">
          {timeframeMismatch ? (
            <p className="explore-strategy-note explore-strategy-note--warn">
              {strategy.name} uses{" "}
              {TIMEFRAME_LABELS[strategyTimeframe(strategy)!]} candles. Chart is{" "}
              {TIMEFRAME_LABELS[chartTimeframe]} — indicators may differ from saved analysis runs.
            </p>
          ) : null}
          {symbolMismatch ? (
            <p className="explore-strategy-note">
              {strategy.name} is not assigned to {symbol}. Overlays use its saved parameters.
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}
