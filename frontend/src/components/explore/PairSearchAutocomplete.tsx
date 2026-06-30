import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import {
  buildOrderedPairSuggestions,
  pairMatchesQuery,
} from "../../lib/exploreRecentPairs";

type PairSearchAutocompleteProps = {
  onSelect: (symbol: string) => void;
  selectedSymbol?: string | null;
};

type PairOption = {
  symbol: string;
  enabled: boolean;
};

export default function PairSearchAutocomplete({
  onSelect,
  selectedSymbol = null,
}: PairSearchAutocompleteProps) {
  const [query, setQuery] = useState(selectedSymbol ?? "");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [options, setOptions] = useState<PairOption[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.getForexPairs();
        if (cancelled) return;
        const enabledSet = new Set(data.enabled_pairs);
        const ordered = buildOrderedPairSuggestions(
          data.catalog,
          data.enabled_pairs,
          data.pair_order,
        );
        setOptions(
          ordered.map((symbol) => ({
            symbol,
            enabled: enabledSet.has(symbol),
          })),
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (selectedSymbol) {
      setQuery(selectedSymbol);
    }
  }, [selectedSymbol]);

  const filtered = useMemo(
    () => options.filter((option) => pairMatchesQuery(option.symbol, query)),
    [options, query],
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [query, filtered.length]);

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

  function selectSymbol(symbol: string) {
    setQuery(symbol);
    setOpen(false);
    onSelect(symbol);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((prev) => Math.min(prev + 1, Math.max(filtered.length - 1, 0)));
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
      const match = filtered[activeIndex];
      if (match) {
        selectSymbol(match.symbol);
      }
      return;
    }
    if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="explore-search" ref={rootRef}>
      <input
        ref={inputRef}
        type="search"
        className="research-search explore-search-input"
        placeholder={loading ? "Loading forex pairs…" : "Search forex pairs…"}
        value={query}
        aria-label="Search forex pairs"
        aria-autocomplete="list"
        aria-expanded={open && filtered.length > 0}
        aria-controls="explore-pair-suggestions"
        role="combobox"
        disabled={loading}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onKeyDown={handleKeyDown}
      />
      {open && filtered.length > 0 ? (
        <ul
          id="explore-pair-suggestions"
          className="explore-search-dropdown"
          role="listbox"
          aria-label="Forex pair suggestions"
        >
          {filtered.map((option, index) => (
            <li key={option.symbol} role="presentation">
              <button
                type="button"
                role="option"
                aria-selected={index === activeIndex}
                className={`explore-search-option${index === activeIndex ? " explore-search-option--active" : ""}`}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => selectSymbol(option.symbol)}
                onMouseEnter={() => setActiveIndex(index)}
              >
                <span>{option.symbol}</span>
                {option.enabled ? <span className="explore-search-badge">Enabled</span> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
