import { useEffect, useMemo, useState } from "react";
import ToggleSwitch from "../../ToggleSwitch";
import SegmentedControl from "./SegmentedControl";
import type { AssetClass } from "../../../api/client";
import {
  ASSET_CLASS_LABELS,
  loadInstrumentCatalog,
  type StrategyAssignmentMode,
} from "../../../lib/strategies/instruments";

type CatalogGroup = {
  assetClass: AssetClass;
  instruments: string[];
};

type StrategyAssignmentFieldsProps = {
  enabled: boolean;
  assignmentMode: StrategyAssignmentMode;
  assetClass: AssetClass;
  selectedInstruments: string[];
  supportedAssetClasses: AssetClass[];
  onEnabledChange: (enabled: boolean) => void;
  onAssignmentModeChange: (mode: StrategyAssignmentMode) => void;
  onAssetClassChange: (assetClass: AssetClass) => void;
  onSelectedInstrumentsChange: (instruments: string[]) => void;
};

export default function StrategyAssignmentFields({
  enabled,
  assignmentMode,
  assetClass,
  selectedInstruments,
  supportedAssetClasses,
  onEnabledChange,
  onAssignmentModeChange,
  onAssetClassChange,
  onSelectedInstrumentsChange,
}: StrategyAssignmentFieldsProps) {
  const [catalogGroups, setCatalogGroups] = useState<CatalogGroup[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || assignmentMode !== "specific") return;
    let cancelled = false;
    setCatalogLoading(true);
    setCatalogError(null);
    Promise.all(
      supportedAssetClasses.map(async (cls) => ({
        assetClass: cls,
        instruments: await loadInstrumentCatalog(cls),
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
  }, [enabled, assignmentMode, supportedAssetClasses]);

  const assetClassOptions = useMemo(
    () =>
      supportedAssetClasses.map((value) => ({
        value,
        label: ASSET_CLASS_LABELS[value],
      })),
    [supportedAssetClasses],
  );

  const allCatalogInstruments = useMemo(
    () => catalogGroups.flatMap((group) => group.instruments),
    [catalogGroups],
  );

  const allSelected =
    allCatalogInstruments.length > 0 &&
    selectedInstruments.length === allCatalogInstruments.length;
  const noneSelected = selectedInstruments.length === 0;

  function toggleInstrument(symbol: string) {
    onSelectedInstrumentsChange(
      selectedInstruments.includes(symbol)
        ? selectedInstruments.filter((s) => s !== symbol)
        : [...selectedInstruments, symbol],
    );
  }

  function selectAll() {
    onSelectedInstrumentsChange([...allCatalogInstruments]);
  }

  function deselectAll() {
    onSelectedInstrumentsChange([]);
  }

  return (
    <>
      <div className="param-toggle-row-header strategy-enable-row">
        <span className="param-control-label">Enable strategy</span>
        <ToggleSwitch
          checked={enabled}
          onChange={onEnabledChange}
          label="Enable strategy"
        />
      </div>

      {enabled && (
        <>
          <SegmentedControl
            label="Assignment"
            value={assignmentMode}
            options={[
              { value: "asset_class", label: "Asset class" },
              { value: "specific", label: "Specific assets" },
            ]}
            onChange={onAssignmentModeChange}
          />

          {assignmentMode === "asset_class" && (
            <>
              <SegmentedControl
                label="Assign to"
                value={assetClass}
                options={assetClassOptions}
                onChange={onAssetClassChange}
              />
              <p className="param-helper">
                Strategy runs on all enabled {ASSET_CLASS_LABELS[assetClass].toLowerCase()}{" "}
                instruments configured in Settings.
              </p>
            </>
          )}

          {assignmentMode === "specific" && (
            <div className="strategy-instrument-picker">
              <div className="strategy-instrument-picker-header">
                <span className="param-control-label">
                  Select assets
                  {selectedInstruments.length > 0
                    ? ` (${selectedInstruments.length} selected)`
                    : ""}
                </span>
                <div className="strategy-instrument-picker-actions">
                  <button
                    type="button"
                    className="btn btn-sm btn-secondary"
                    disabled={allSelected || allCatalogInstruments.length === 0}
                    onClick={selectAll}
                  >
                    All
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-secondary"
                    disabled={noneSelected}
                    onClick={deselectAll}
                  >
                    None
                  </button>
                </div>
              </div>

              {catalogLoading && (
                <p className="settings-muted strategy-instrument-picker-status">Loading…</p>
              )}
              {catalogError && !catalogLoading && (
                <p className="settings-error strategy-instrument-picker-status">{catalogError}</p>
              )}
              {!catalogLoading && !catalogError && allCatalogInstruments.length === 0 && (
                <p className="settings-muted strategy-instrument-picker-status">
                  No instruments available.
                </p>
              )}
              {!catalogLoading &&
                catalogGroups.map((group) =>
                  group.instruments.length === 0 ? null : (
                    <div key={group.assetClass} className="strategy-instrument-group">
                      <span className="strategy-instrument-group-label">
                        {ASSET_CLASS_LABELS[group.assetClass]}
                      </span>
                      <div className="strategy-instrument-grid">
                        {group.instruments.map((symbol) => {
                          const checked = selectedInstruments.includes(symbol);
                          return (
                            <label
                              key={symbol}
                              className={`forex-pair-checkbox strategy-instrument-checkbox${
                                checked ? " forex-pair-checkbox--checked" : ""
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleInstrument(symbol)}
                              />
                              <span className="forex-pair-label">{symbol}</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ),
                )}
              {noneSelected && allCatalogInstruments.length > 0 && (
                <p className="param-helper param-helper--warn">
                  Select at least one asset to assign this strategy.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </>
  );
}
