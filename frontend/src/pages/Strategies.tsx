import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Minus, Trash2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api, type AssetClass, type Strategy } from "../api/client";
import { TIMEFRAME_LABELS, type Timeframe } from "../lib/strategyParams";
import AssetClassFilterSelect from "../components/AssetClassFilterSelect";
import StrategyTemplatesSection from "../components/strategies/StrategyTemplatesSection";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import {
  ASSET_CLASS_LABELS,
  instrumentSelectionSummary,
  isWatchlistAllSelection,
} from "./strategies/strategyAssignment";

function instrumentSummary(strategy: Strategy): string {
  const summary = instrumentSelectionSummary(strategy.instrument_selection);
  if (summary) return summary;

  const count = strategy.instruments.length;
  if (count === 0) {
    const selection = strategy.instrument_selection;
    if (selection) {
      const watchlistClasses = Object.entries(selection)
        .filter(([, syms]) => isWatchlistAllSelection(syms))
        .map(([cls]) => ASSET_CLASS_LABELS[cls as AssetClass]);
      if (watchlistClasses.length > 0) {
        return watchlistClasses.map((label) => `${label} watchlist`).join(", ");
      }
    }
    return "—";
  }
  const unit = strategy.asset_class === "forex" ? "pair" : "symbol";
  return `${count} ${unit}${count === 1 ? "" : "s"}`;
}

function formatWinRate(rate: number | null): string {
  if (rate === null) return "—";
  return `${(rate * 100).toFixed(1)}%`;
}

function formatPnl(value: number): string {
  const formatted = Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (value > 0) return `+$${formatted}`;
  if (value < 0) return `-$${formatted}`;
  return "$0.00";
}

function pnlClass(value: number): string {
  if (value > 0) return "strategy-stat--positive";
  if (value < 0) return "strategy-stat--negative";
  return "strategy-stat--neutral";
}

function strategyTypeLabel(strategy: Strategy): string {
  return strategy.strategy_type === "preset" ? "Template" : "Custom";
}

function strategyTimeframeLabel(strategy: Strategy): string {
  const timeframe = strategy.timeframe ?? strategy.params?.timeframe;
  if (!timeframe) return "—";
  return TIMEFRAME_LABELS[timeframe as Timeframe] ?? timeframe;
}

function normalizeStrategies(apiStrategies: Strategy[]): Strategy[] {
  return apiStrategies.map((strategy) => ({
    ...strategy,
    strategy_type: strategy.strategy_type ?? (strategy.preset_id ? "preset" : "custom"),
  }));
}

export default function Strategies() {
  const navigate = useNavigate();
  const { formatInstant } = useGeneralSettings();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [assetClassFilter, setAssetClassFilter] = useState<Set<AssetClass>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkPending, setBulkPending] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const actionsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .listStrategies()
      .then((data) => setStrategies(normalizeStrategies(data.strategies)))
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load strategies");
        setStrategies([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return strategies.filter((strategy) => {
      if (assetClassFilter.size > 0 && !assetClassFilter.has(strategy.asset_class)) {
        return false;
      }
      if (!q) return true;
      const haystack = [
        strategy.name,
        strategy.asset_class_label,
        strategy.description,
        strategyTypeLabel(strategy),
        ...strategy.instruments,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [strategies, query, assetClassFilter]);

  const filteredIds = useMemo(() => filtered.map((strategy) => strategy.id), [filtered]);
  const selectedFilteredCount = useMemo(
    () => filteredIds.filter((id) => selectedIds.has(id)).length,
    [filteredIds, selectedIds],
  );
  const allFilteredSelected =
    filteredIds.length > 0 && selectedFilteredCount === filteredIds.length;
  const someFilteredSelected =
    selectedFilteredCount > 0 && selectedFilteredCount < filteredIds.length;

  useEffect(() => {
    const checkbox = selectAllRef.current;
    if (!checkbox) return;
    checkbox.indeterminate = someFilteredSelected;
    checkbox.checked = allFilteredSelected;
  }, [allFilteredSelected, someFilteredSelected]);

  useEffect(() => {
    if (!actionsOpen) return;

    function handleClick(event: MouseEvent) {
      if (actionsRef.current && !actionsRef.current.contains(event.target as Node)) {
        setActionsOpen(false);
      }
    }

    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") setActionsOpen(false);
    }

    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [actionsOpen]);

  useEffect(() => {
    if (selectedFilteredCount === 0) {
      setActionsOpen(false);
    }
  }, [selectedFilteredCount]);

  function toggleSelected(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleSelectAllFiltered() {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allFilteredSelected) {
        for (const id of filteredIds) {
          next.delete(id);
        }
      } else {
        for (const id of filteredIds) {
          next.add(id);
        }
      }
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
    setBulkError(null);
  }

  async function applyBulkEnabled(enabled: boolean) {
    const ids = filteredIds.filter((id) => selectedIds.has(id));
    if (ids.length === 0) return;

    setBulkPending(true);
    setBulkError(null);

    try {
      const results = await Promise.allSettled(
        ids.map((id) => api.updateStrategy(id, { enabled })),
      );
      const failed = results.filter((result) => result.status === "rejected").length;
      if (failed > 0) {
        setBulkError(
          failed === ids.length
            ? `Could not ${enabled ? "enable" : "disable"} selected strategies.`
            : `${failed} of ${ids.length} strategies could not be updated.`,
        );
      }

      const updatedIds = new Set(
        results
          .map((result, index) => (result.status === "fulfilled" ? ids[index] : null))
          .filter((id): id is string => id !== null),
      );

      if (updatedIds.size > 0) {
        setStrategies((current) =>
          current.map((strategy) =>
            updatedIds.has(strategy.id) ? { ...strategy, enabled } : strategy,
          ),
        );
      }
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Bulk update failed");
    } finally {
      setBulkPending(false);
    }
  }

  async function applyBulkDelete() {
    const ids = filteredIds.filter((id) => selectedIds.has(id));
    if (ids.length === 0) return;

    setBulkPending(true);
    setBulkError(null);

    try {
      const results = await Promise.allSettled(ids.map((id) => api.deleteStrategy(id)));
      const failed = results.filter((result) => result.status === "rejected").length;
      if (failed > 0) {
        setBulkError(
          failed === ids.length
            ? "Could not delete selected strategies."
            : `${failed} of ${ids.length} strategies could not be deleted.`,
        );
      }

      const deletedIds = new Set(
        results
          .map((result, index) => (result.status === "fulfilled" ? ids[index] : null))
          .filter((id): id is string => id !== null),
      );

      if (deletedIds.size > 0) {
        setStrategies((current) => current.filter((strategy) => !deletedIds.has(strategy.id)));
        setSelectedIds((current) => {
          const next = new Set(current);
          for (const id of deletedIds) {
            next.delete(id);
          }
          return next;
        });
      }

      setDeleteConfirmOpen(false);
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Bulk delete failed");
    } finally {
      setBulkPending(false);
    }
  }

  function openDeleteConfirm() {
    setActionsOpen(false);
    setDeleteConfirmOpen(true);
  }

  function stopDialogActivation(event: React.MouseEvent | React.KeyboardEvent) {
    event.stopPropagation();
  }

  function openStrategy(strategy: Strategy) {
    if (strategy.route) {
      navigate(strategy.route);
    }
  }

  const hasSavedStrategies = strategies.length > 0;
  const hasFilteredResults = filtered.length > 0;
  const hasSelection = selectedFilteredCount > 0;

  return (
    <div>
      <h1 className="page-title">Strategies</h1>

      <StrategyTemplatesSection />

      <div className="settings-panel strategy-saved-panel">
        <div className="settings-panel-header">
          <h2 className="settings-subtitle">Your strategies</h2>
        </div>

        {hasSavedStrategies && (
          <div className="research-filters">
            <input
              type="search"
              className="research-search"
              placeholder="Search by name, type, asset class, or instrument…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <AssetClassFilterSelect value={assetClassFilter} onChange={setAssetClassFilter} />
            <div
              className={`research-multiselect strategy-bulk-actions-menu${
                hasSelection ? " strategy-bulk-actions-menu--active" : ""
              }`}
              ref={actionsRef}
            >
              <div className="research-multiselect-wrap">
                <button
                  type="button"
                  className="research-multiselect-trigger strategy-bulk-actions-trigger"
                  disabled={!hasSelection || bulkPending}
                  onClick={() => setActionsOpen((prev) => !prev)}
                  aria-haspopup="menu"
                  aria-expanded={actionsOpen}
                  aria-label="Strategy bulk actions"
                >
                  {hasSelection ? `Actions (${selectedFilteredCount})` : "Actions"}
                </button>
              </div>
              {actionsOpen && hasSelection ? (
                <div className="strategy-bulk-actions-dropdown" role="menu">
                  <p className="strategy-bulk-actions-dropdown-header">
                    {selectedFilteredCount} selected
                  </p>
                  <button
                    type="button"
                    className="strategy-bulk-action-item strategy-bulk-action-item--enable"
                    role="menuitem"
                    disabled={bulkPending}
                    onClick={() => {
                      setActionsOpen(false);
                      void applyBulkEnabled(true);
                    }}
                  >
                    <span className="strategy-bulk-action-icon" aria-hidden>
                      <Check size={15} strokeWidth={2.25} />
                    </span>
                    Enable selected
                  </button>
                  <button
                    type="button"
                    className="strategy-bulk-action-item strategy-bulk-action-item--disable"
                    role="menuitem"
                    disabled={bulkPending}
                    onClick={() => {
                      setActionsOpen(false);
                      void applyBulkEnabled(false);
                    }}
                  >
                    <span className="strategy-bulk-action-icon" aria-hidden>
                      <Minus size={15} strokeWidth={2.25} />
                    </span>
                    Disable selected
                  </button>
                  <div className="strategy-bulk-actions-divider" role="separator" />
                  <button
                    type="button"
                    className="strategy-bulk-action-item strategy-bulk-action-item--clear"
                    role="menuitem"
                    disabled={bulkPending}
                    onClick={() => {
                      setActionsOpen(false);
                      clearSelection();
                    }}
                  >
                    <span className="strategy-bulk-action-icon" aria-hidden>
                      <X size={15} strokeWidth={2.25} />
                    </span>
                    Clear selection
                  </button>
                  <div className="strategy-bulk-actions-divider" role="separator" />
                  <button
                    type="button"
                    className="strategy-bulk-action-item strategy-bulk-action-item--delete"
                    role="menuitem"
                    disabled={bulkPending}
                    onClick={openDeleteConfirm}
                  >
                    <span className="strategy-bulk-action-icon" aria-hidden>
                      <Trash2 size={15} strokeWidth={2.25} />
                    </span>
                    Delete selected
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        )}

        {bulkError && !loading && <p className="settings-error">{bulkError}</p>}

        {loading && <p className="settings-muted">Loading strategies…</p>}
        {error && !loading && <p className="settings-error">{error}</p>}

        {!loading && !error && !hasSavedStrategies && (
          <div className="research-empty-callout strategy-empty-callout">
            <p className="research-empty-callout-title">No strategies yet</p>
            <p className="settings-muted">
              Choose a template above to configure parameters and save your first strategy.
            </p>
          </div>
        )}

        {!loading && !error && hasSavedStrategies && !hasFilteredResults && (
          <p className="settings-muted">No strategies match your filters.</p>
        )}

        {!loading && !error && hasSavedStrategies && hasFilteredResults && (
          <div className="research-table-wrap">
            <table className="research-table strategy-table">
              <thead>
                <tr>
                  <th className="strategy-table-checkbox-col" scope="col">
                    <label className="strategy-table-checkbox-label">
                      <input
                        ref={selectAllRef}
                        type="checkbox"
                        className="ui-checkbox-input"
                        checked={allFilteredSelected}
                        onChange={toggleSelectAllFiltered}
                        aria-label="Select all visible strategies"
                      />
                    </label>
                  </th>
                  <th>Strategy</th>
                  <th>Timeframe</th>
                  <th>Type</th>
                  <th>Asset class</th>
                  <th>Status</th>
                  <th>Instruments</th>
                  <th>Trades</th>
                  <th>Win rate</th>
                  <th>Realized P&amp;L</th>
                  <th>Open</th>
                  <th>Last trade</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((strategy) => {
                  const isSelected = selectedIds.has(strategy.id);
                  return (
                  <tr
                    key={strategy.id}
                    className={[
                      strategy.route ? "strategy-table-row--clickable" : undefined,
                      isSelected ? "strategy-table-row--selected" : undefined,
                    ]
                      .filter(Boolean)
                      .join(" ") || undefined}
                    onClick={() => openStrategy(strategy)}
                    onKeyDown={(e) => {
                      if (strategy.route && (e.key === "Enter" || e.key === " ")) {
                        e.preventDefault();
                        openStrategy(strategy);
                      }
                    }}
                    tabIndex={strategy.route ? 0 : undefined}
                    role={strategy.route ? "link" : undefined}
                    aria-selected={isSelected}
                  >
                    <td
                      className="strategy-table-checkbox-col"
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.stopPropagation()}
                    >
                      <label className="strategy-table-checkbox-label">
                        <input
                          type="checkbox"
                          className="ui-checkbox-input"
                          checked={isSelected}
                          onChange={() => toggleSelected(strategy.id)}
                          aria-label={`Select ${strategy.name}`}
                        />
                      </label>
                    </td>
                    <td>
                      <div className="strategy-name-cell">
                        <span className="strategy-name">{strategy.name}</span>
                        {strategy.description ? (
                          <span className="strategy-description">{strategy.description}</span>
                        ) : null}
                      </div>
                    </td>
                    <td>{strategyTimeframeLabel(strategy)}</td>
                    <td>
                      <span
                        className={`research-tag strategy-type-tag strategy-type-tag--${
                          strategy.strategy_type === "preset" ? "template" : "custom"
                        }`}
                      >
                        {strategyTypeLabel(strategy)}
                      </span>
                    </td>
                    <td>{strategy.asset_class_label}</td>
                    <td>
                      <span
                        className={`research-tag strategy-status--${
                          strategy.enabled ? "enabled" : "disabled"
                        }`}
                      >
                        {strategy.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </td>
                    <td className="settings-muted">{instrumentSummary(strategy)}</td>
                    <td>{strategy.stats.total_trades}</td>
                    <td>{formatWinRate(strategy.stats.win_rate)}</td>
                    <td className={pnlClass(strategy.stats.realized_pnl)}>
                      {formatPnl(strategy.stats.realized_pnl)}
                    </td>
                    <td>{strategy.stats.open_positions}</td>
                    <td className="settings-muted">
                      {formatInstant(strategy.stats.last_trade_at, "short")}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {deleteConfirmOpen && (
        <div
          className="confirm-overlay"
          role="presentation"
          onClick={() => !bulkPending && setDeleteConfirmOpen(false)}
        >
          <div
            className="confirm-dialog confirm-dialog--error"
            role="alertdialog"
            aria-labelledby="delete-strategies-title"
            aria-describedby="delete-strategies-message"
            onClick={stopDialogActivation}
          >
            <h4 id="delete-strategies-title">
              Delete {selectedFilteredCount === 1 ? "strategy" : "strategies"}?
            </h4>
            <p id="delete-strategies-message">
              This will permanently delete{" "}
              <strong>
                {selectedFilteredCount} strateg{selectedFilteredCount === 1 ? "y" : "ies"}
              </strong>
              . This cannot be undone.
            </p>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={bulkPending}
                onClick={() => setDeleteConfirmOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={bulkPending}
                onClick={() => void applyBulkDelete()}
              >
                {bulkPending ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
