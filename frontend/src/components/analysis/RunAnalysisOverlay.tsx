import { useEffect, useMemo, useState } from "react";
import type { AssetClass } from "../../api/client";
import { api, type Strategy } from "../../api/client";
import { strategyCoversSymbol } from "../../lib/exploreStrategySelection";
import { TIMEFRAME_LABELS } from "../../lib/strategyParams";
import {
  ALL_ASSET_CLASSES,
  emptyInstrumentSelection,
  hasInstrumentSelection,
  isWatchlistAllSelection,
  specificSymbols,
  type StrategyInstrumentSelection,
} from "../../lib/strategies/instruments";
import StrategyOverlay from "../strategies/StrategyOverlay";
import StrategyAssetTreePicker from "../strategies/StrategyAssetTreePicker";

type RunAnalysisOverlayProps = {
  onClose: () => void;
  onRunComplete: (runId: string) => void;
};

type AnalysisTarget = {
  assetClass: AssetClass;
  symbol: string;
};

type SelectionIssue =
  | null
  | "none"
  | "watchlist_all"
  | "multiple_symbols"
  | "multiple_asset_classes";

function resolveSingleAnalysisTarget(
  selection: StrategyInstrumentSelection,
): { target: AnalysisTarget | null; issue: SelectionIssue } {
  const activeClasses = ALL_ASSET_CLASSES.filter((assetClass) => {
    const symbols = selection[assetClass];
    return Boolean(symbols?.length);
  });

  if (activeClasses.length === 0) {
    return { target: null, issue: "none" };
  }

  if (activeClasses.length > 1) {
    return { target: null, issue: "multiple_asset_classes" };
  }

  const assetClass = activeClasses[0];
  const symbols = selection[assetClass] ?? [];

  if (isWatchlistAllSelection(symbols)) {
    return { target: null, issue: "watchlist_all" };
  }

  const specific = specificSymbols(symbols);
  if (specific.length === 0) {
    return { target: null, issue: "none" };
  }
  if (specific.length > 1) {
    return { target: null, issue: "multiple_symbols" };
  }

  return {
    target: { assetClass, symbol: specific[0] },
    issue: null,
  };
}

function selectionIssueMessage(issue: SelectionIssue): string | null {
  switch (issue) {
    case "watchlist_all":
      return "One-off runs require a specific symbol. Expand the asset class and pick one instrument.";
    case "multiple_symbols":
      return "Select only one symbol for a one-off run.";
    case "multiple_asset_classes":
      return "Select instruments from only one asset class for a one-off run.";
    case "none":
      return "Select at least one asset to run analysis.";
    default:
      return null;
  }
}

function strategyMatchesTarget(strategy: Strategy, target: AnalysisTarget | null): boolean {
  if (!target) return false;
  if (strategy.asset_class !== target.assetClass) return false;
  return strategyCoversSymbol(strategy, target.symbol);
}

export default function RunAnalysisOverlay({ onClose, onRunComplete }: RunAnalysisOverlayProps) {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loadingStrategies, setLoadingStrategies] = useState(true);
  const [strategyError, setStrategyError] = useState<string | null>(null);
  const [instrumentSelection, setInstrumentSelection] =
    useState<StrategyInstrumentSelection>(emptyInstrumentSelection());
  const [strategyId, setStrategyId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { target, issue } = useMemo(
    () => resolveSingleAnalysisTarget(instrumentSelection),
    [instrumentSelection],
  );
  const selectionMessage = selectionIssueMessage(issue);

  useEffect(() => {
    let cancelled = false;
    setLoadingStrategies(true);
    setStrategyError(null);

    api
      .listStrategies()
      .then((data) => {
        if (!cancelled) setStrategies(data.strategies);
      })
      .catch((err) => {
        if (!cancelled) {
          setStrategyError(err instanceof Error ? err.message : "Failed to load strategies");
          setStrategies([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingStrategies(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const eligibleStrategies = useMemo(
    () =>
      [...strategies]
        .filter((strategy) => strategyMatchesTarget(strategy, target))
        .sort((a, b) => a.name.localeCompare(b.name)),
    [strategies, target],
  );

  useEffect(() => {
    if (!strategyId) return;
    if (!eligibleStrategies.some((strategy) => strategy.id === strategyId)) {
      setStrategyId("");
    }
  }, [eligibleStrategies, strategyId]);

  const selectedStrategy = eligibleStrategies.find((strategy) => strategy.id === strategyId);
  const canSubmit = Boolean(target && strategyId && !submitting);

  async function handleSubmit() {
    if (!target || !strategyId || submitting) return;

    setSubmitting(true);
    setError(null);
    try {
      const run = await api.runStrategyAnalysis({
        strategy_id: strategyId,
        asset_class: target.assetClass,
        symbol: target.symbol,
      });
      onRunComplete(run.id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run analysis");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <StrategyOverlay onClose={onClose} wide titleId="run-analysis-title">
      <div className="model-overlay-body">
        <h4 className="model-overlay-title" id="run-analysis-title">
          Run analysis
        </h4>
        <p className="model-overlay-desc">
          Choose an instrument and strategy to run a one-off analysis against the latest candle
          data.
        </p>

        <div className="settings-form model-overlay-form run-analysis-form">
          <StrategyAssetTreePicker
            value={instrumentSelection}
            onChange={setInstrumentSelection}
          />

          {hasInstrumentSelection(instrumentSelection) && selectionMessage && (
            <p className="param-helper param-helper--warn">{selectionMessage}</p>
          )}

          <div className="param-control">
            <label htmlFor="run-analysis-strategy" className="param-control-label">
              Strategy
              <span className="param-control-required">Required</span>
            </label>
            {loadingStrategies && (
              <p className="settings-muted strategy-instrument-picker-status">Loading strategies…</p>
            )}
            {strategyError && !loadingStrategies && (
              <p className="settings-error strategy-instrument-picker-status">{strategyError}</p>
            )}
            {!loadingStrategies && !strategyError && (
              <>
                <div className="research-select-wrap">
                  <select
                    id="run-analysis-strategy"
                    className="research-select"
                    value={strategyId}
                    onChange={(event) => setStrategyId(event.target.value)}
                    disabled={!target || eligibleStrategies.length === 0 || submitting}
                  >
                    <option value="">
                      {!target
                        ? "Select one instrument first"
                        : eligibleStrategies.length === 0
                          ? "No strategies cover this instrument"
                          : "Choose a strategy"}
                    </option>
                    {eligibleStrategies.map((strategy) => (
                      <option key={strategy.id} value={strategy.id}>
                        {strategy.name}
                        {!strategy.enabled ? " (disabled)" : ""}
                      </option>
                    ))}
                  </select>
                </div>
                {selectedStrategy?.timeframe && (
                  <p className="param-helper">
                    Timeframe:{" "}
                    {TIMEFRAME_LABELS[selectedStrategy.timeframe] ?? selectedStrategy.timeframe}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      <div className="model-overlay-footer">
        {error && <p className="settings-error model-overlay-feedback">{error}</p>}
        <div className="confirm-actions model-overlay-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <div className="model-overlay-actions-primary">
            <button type="button" className="btn" onClick={() => void handleSubmit()} disabled={!canSubmit}>
              {submitting ? "Running…" : "Run analysis"}
            </button>
          </div>
        </div>
      </div>
    </StrategyOverlay>
  );
}
