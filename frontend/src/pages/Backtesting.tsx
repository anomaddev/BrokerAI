import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, History, Trash2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  api,
  type AssetClass,
  type BacktestRun,
  type BacktestRunStatus,
} from "../api/client";
import AssetClassFilterSelect from "../components/AssetClassFilterSelect";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import {
  backtestRunTimeframeLabel,
  sortBacktestRuns,
  type BacktestRunSortKey,
  type SortDirection,
} from "../lib/backtests/backtestRunSort";
import {
  backtestRunStatusLabel,
  normalizeBacktestRunStatus,
} from "../lib/backtests/backtestRunStatus";
import { ROUTES } from "../lib/routes";

type StatusFilter = "all" | BacktestRunStatus;

function formatWinRate(rate: number | null): string {
  if (rate === null) return "—";
  return `${(rate * 100).toFixed(1)}%`;
}

function formatPnl(value: number | null): string {
  if (value === null) return "—";
  const formatted = Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (value > 0) return `+$${formatted}`;
  if (value < 0) return `-$${formatted}`;
  return "$0.00";
}

function pnlClass(value: number | null): string {
  if (value == null) return "strategy-stat--neutral";
  if (value > 0) return "strategy-stat--positive";
  if (value < 0) return "strategy-stat--negative";
  return "strategy-stat--neutral";
}

function formatTrades(value: number | null): string {
  if (value === null) return "—";
  return String(value);
}

function normalizeRuns(runs: BacktestRun[]): BacktestRun[] {
  return runs.map((run) => ({
    ...run,
    status: normalizeBacktestRunStatus(run.status),
    instruments: run.instruments ?? [],
    stats: {
      total_trades: run.stats?.total_trades ?? null,
      win_rate: run.stats?.win_rate ?? null,
      realized_pnl: run.stats?.realized_pnl ?? null,
      max_drawdown: run.stats?.max_drawdown ?? null,
    },
  }));
}

type SortableHeaderProps = {
  label: string;
  sortKey: BacktestRunSortKey;
  activeKey: BacktestRunSortKey;
  direction: SortDirection;
  onSort: (key: BacktestRunSortKey) => void;
};

function SortableHeader({ label, sortKey, activeKey, direction, onSort }: SortableHeaderProps) {
  const active = activeKey === sortKey;
  return (
    <th scope="col" aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        className={`strategy-table-sort-btn${active ? " strategy-table-sort-btn--active" : ""}`}
        onClick={() => onSort(sortKey)}
      >
        <span>{label}</span>
        {active ? (
          direction === "asc" ? (
            <ChevronUp size={14} aria-hidden />
          ) : (
            <ChevronDown size={14} aria-hidden />
          )
        ) : null}
      </button>
    </th>
  );
}

export default function Backtesting() {
  const navigate = useNavigate();
  const { formatInstant } = useGeneralSettings();
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [assetClassFilter, setAssetClassFilter] = useState<Set<AssetClass>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkPending, setBulkPending] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [sortKey, setSortKey] = useState<BacktestRunSortKey>("created");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const selectAllRef = useRef<HTMLInputElement>(null);
  const actionsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .listBacktestRuns({ limit: 200 })
      .then((data) => setRuns(normalizeRuns(data.runs)))
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load backtest runs");
        setRuns([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matched = runs.filter((run) => {
      if (statusFilter !== "all" && normalizeBacktestRunStatus(run.status) !== statusFilter) {
        return false;
      }
      if (
        assetClassFilter.size > 0 &&
        !assetClassFilter.has(run.asset_class as AssetClass)
      ) {
        return false;
      }
      if (!q) return true;
      const haystack = [
        run.strategy_name,
        run.asset_class_label,
        backtestRunTimeframeLabel(run),
        backtestRunStatusLabel(run.status),
        ...run.instruments,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
    return sortBacktestRuns(matched, sortKey, sortDirection);
  }, [runs, query, statusFilter, assetClassFilter, sortKey, sortDirection]);

  const filteredIds = useMemo(() => filtered.map((run) => run.id), [filtered]);
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

  function handleSort(key: BacktestRunSortKey) {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection(key === "created" || key === "finished" ? "desc" : "asc");
  }

  async function applyBulkRerun() {
    const selectedRuns = filtered.filter((run) => selectedIds.has(run.id));
    const strategyIds = [...new Set(selectedRuns.map((run) => run.strategy_id))];
    if (strategyIds.length === 0) return;

    setBulkPending(true);
    setBulkError(null);
    setActionsOpen(false);

    try {
      const result = await api.queueStrategyBacktests(strategyIds);
      const newRuns = normalizeRuns(result.runs ?? []);
      if (newRuns.length > 0) {
        setRuns((current) => [...newRuns, ...current]);
      }
      if (result.queued < strategyIds.length) {
        setBulkError(
          `${result.queued} of ${strategyIds.length} strategies were queued for backtest.`,
        );
      }
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Could not queue backtests");
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
      const results = await Promise.allSettled(ids.map((id) => api.deleteBacktestRun(id)));
      const failed = results.filter((result) => result.status === "rejected").length;
      if (failed > 0) {
        setBulkError(
          failed === ids.length
            ? "Could not delete selected backtest runs."
            : `${failed} of ${ids.length} backtest runs could not be deleted.`,
        );
      }

      const deletedIds = new Set(
        results
          .map((result, index) => (result.status === "fulfilled" ? ids[index] : null))
          .filter((id): id is string => id !== null),
      );

      if (deletedIds.size > 0) {
        setRuns((current) => current.filter((run) => !deletedIds.has(run.id)));
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

  function openRun(run: BacktestRun) {
    navigate(ROUTES.research.strategyEdit(run.strategy_id));
  }

  const hasFilteredResults = filtered.length > 0;
  const hasSelection = selectedFilteredCount > 0;
  const emptyMessage = loading
    ? "Loading backtest runs…"
    : error
      ? error
      : runs.length === 0
        ? "No backtests yet. Queue a backtest from the Strategies page to see it here."
        : "No backtest runs match your filters.";

  return (
    <div>
      <div className="strategy-list-header">
        <h1 className="page-title">Backtesting</h1>
      </div>
      <p className="settings-muted">
        Replay historical candles against saved strategies. Previous runs appear below.
      </p>

      <div className="settings-panel strategy-saved-panel">
        <div className="research-filters">
          <input
            type="search"
            className="research-search"
            placeholder="Search by strategy, timeframe, or instrument…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="research-select-wrap">
            <select
              className="research-select"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
              aria-label="Filter by status"
            >
              <option value="all">All statuses</option>
              <option value="queued">Queued</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>
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
                aria-label="Backtest run bulk actions"
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
                  className="strategy-bulk-action-item strategy-bulk-action-item--backtest"
                  role="menuitem"
                  disabled={bulkPending}
                  onClick={() => {
                    void applyBulkRerun();
                  }}
                >
                  <span className="strategy-bulk-action-icon" aria-hidden>
                    <History size={15} strokeWidth={2.25} />
                  </span>
                  Re-run selected
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

        {bulkError && !loading && <p className="settings-error">{bulkError}</p>}

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
                      disabled={!hasFilteredResults}
                      aria-label="Select all visible backtest runs"
                    />
                  </label>
                </th>
                <SortableHeader
                  label="Strategy"
                  sortKey="strategy"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Timeframe"
                  sortKey="timeframe"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Asset class"
                  sortKey="assetClass"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Status"
                  sortKey="status"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Created"
                  sortKey="created"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Finished"
                  sortKey="finished"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Trades"
                  sortKey="trades"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Win rate"
                  sortKey="winRate"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Realized P&L"
                  sortKey="pnl"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
              </tr>
            </thead>
            <tbody>
              {!hasFilteredResults ? (
                <tr className="strategy-table-empty-row">
                  <td colSpan={10}>
                    <div className="strategy-table-empty">
                      <p className={error && !loading ? "settings-error" : "settings-muted"}>
                        {emptyMessage}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                filtered.map((run) => {
                  const isSelected = selectedIds.has(run.id);
                  const status = normalizeBacktestRunStatus(run.status);
                  return (
                    <tr
                      key={run.id}
                      className={[
                        "strategy-table-row--clickable",
                        isSelected ? "strategy-table-row--selected" : undefined,
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      onClick={() => openRun(run)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openRun(run);
                        }
                      }}
                      tabIndex={0}
                      role="link"
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
                            onChange={() => toggleSelected(run.id)}
                            aria-label={`Select backtest for ${run.strategy_name}`}
                          />
                        </label>
                      </td>
                      <td>
                        <div className="strategy-name-cell">
                          <span className="strategy-name">{run.strategy_name}</span>
                        </div>
                      </td>
                      <td>{backtestRunTimeframeLabel(run)}</td>
                      <td>{run.asset_class_label || "—"}</td>
                      <td>
                        <span className={`research-tag strategy-backtest--${status}`}>
                          {backtestRunStatusLabel(status)}
                        </span>
                      </td>
                      <td className="settings-muted">
                        {formatInstant(run.created_at, "short")}
                      </td>
                      <td className="settings-muted">
                        {formatInstant(run.finished_at, "short")}
                      </td>
                      <td>{formatTrades(run.stats.total_trades)}</td>
                      <td>{formatWinRate(run.stats.win_rate)}</td>
                      <td className={pnlClass(run.stats.realized_pnl)}>
                        {formatPnl(run.stats.realized_pnl)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
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
            aria-labelledby="delete-backtest-runs-title"
            aria-describedby="delete-backtest-runs-message"
            onClick={stopDialogActivation}
          >
            <h4 id="delete-backtest-runs-title">
              Delete {selectedFilteredCount === 1 ? "backtest run" : "backtest runs"}?
            </h4>
            <p id="delete-backtest-runs-message">
              This will permanently delete{" "}
              <strong>
                {selectedFilteredCount} backtest run
                {selectedFilteredCount === 1 ? "" : "s"}
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
