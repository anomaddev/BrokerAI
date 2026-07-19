import { useState } from "react";
import { X } from "lucide-react";
import type { AssetClass } from "../../api/client";
import {
  ALL_ASSET_CLASSES,
  type StrategyInstrumentSelection,
} from "../../lib/strategies/instruments";
import { STRATEGY_TITLE_MAX, clampStrategyTitle } from "../../lib/strategyBuilder/components";
import StrategyAssetPills from "./StrategyAssetPills";

type StrategyBuilderHeaderProps = {
  title: string;
  onTitleChange: (value: string) => void;
  instrumentSelection: StrategyInstrumentSelection;
  onInstrumentSelectionChange: (selection: StrategyInstrumentSelection) => void;
  supportedAssetClasses?: AssetClass[];
  onClose: () => void;
  currentVersion?: number | null;
};

export default function StrategyBuilderHeader({
  title,
  onTitleChange,
  instrumentSelection,
  onInstrumentSelectionChange,
  supportedAssetClasses = ALL_ASSET_CLASSES,
  onClose,
  currentVersion = null,
}: StrategyBuilderHeaderProps) {
  const [titleFocused, setTitleFocused] = useState(false);

  return (
    <div className="strategy-builder-top-row">
      <div className="strategy-chart-area-bar">
        <div className="strategy-builder-header-bar">
          <div className="strategy-builder-title-row">
            <button
              type="button"
              className="strategy-builder-close-btn"
              onClick={onClose}
              aria-label="Close strategy builder"
              title="Close"
            >
              <X size={18} aria-hidden="true" />
            </button>
            <label className="strategy-builder-title-field">
              <span className="visually-hidden">Strategy name</span>
              <input
                type="text"
                className="strategy-builder-title-input"
                value={title}
                maxLength={STRATEGY_TITLE_MAX}
                onChange={(event) => onTitleChange(clampStrategyTitle(event.target.value))}
                onFocus={() => setTitleFocused(true)}
                onBlur={() => setTitleFocused(false)}
                placeholder="Strategy name"
                autoComplete="off"
              />
              {titleFocused ? (
                <span className="strategy-builder-title-count">
                  {title.length}/{STRATEGY_TITLE_MAX}
                </span>
              ) : null}
            </label>
          </div>
          <StrategyAssetPills
            value={instrumentSelection}
            onChange={onInstrumentSelectionChange}
            supportedAssetClasses={supportedAssetClasses}
          />
        </div>
      </div>
      <div className="strategy-builder-panel-header strategy-builder-panel-header--paired">
        <h2 className="strategy-builder-panel-title">Parameters</h2>
        {currentVersion != null ? (
          <span className="strategy-builder-current-version" title="Currently saved version">
            v{currentVersion}
          </span>
        ) : null}
      </div>
    </div>
  );
}
