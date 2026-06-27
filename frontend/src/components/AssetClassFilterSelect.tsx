import { useEffect, useRef, useState } from "react";
import type { AssetClass } from "../api/client";
import { ASSET_CLASS_LABELS } from "../lib/strategies/instruments";

const ASSET_CLASS_OPTIONS = Object.entries(ASSET_CLASS_LABELS).map(([value, label]) => ({
  value: value as AssetClass,
  label,
}));

type AssetClassFilterSelectProps = {
  value: Set<AssetClass>;
  onChange: (value: Set<AssetClass>) => void;
};

function filterLabel(selected: Set<AssetClass>): string {
  if (selected.size === 0 || selected.size === ASSET_CLASS_OPTIONS.length) {
    return "All asset classes";
  }
  const labels = ASSET_CLASS_OPTIONS.filter((option) => selected.has(option.value)).map(
    (option) => option.label,
  );
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return labels.join(", ");
  return `${labels.length} asset classes`;
}

export default function AssetClassFilterSelect({ value, onChange }: AssetClassFilterSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function handleClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  function toggleAssetClass(assetClass: AssetClass) {
    const next = new Set(value);
    if (next.has(assetClass)) {
      next.delete(assetClass);
    } else {
      next.add(assetClass);
    }
    onChange(next);
  }

  return (
    <div className="research-multiselect" ref={rootRef}>
      <div className="research-multiselect-wrap">
        <button
          type="button"
          className="research-multiselect-trigger"
          onClick={() => setOpen((prev) => !prev)}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label="Filter by asset class"
        >
          {filterLabel(value)}
        </button>
      </div>
      {open ? (
        <div className="research-multiselect-panel" role="listbox" aria-multiselectable="true">
          {ASSET_CLASS_OPTIONS.map((option) => {
            const checked = value.has(option.value);
            return (
              <label
                key={option.value}
                className={`research-multiselect-option${checked ? " research-multiselect-option--checked" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleAssetClass(option.value)}
                />
                <span>{option.label}</span>
              </label>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
