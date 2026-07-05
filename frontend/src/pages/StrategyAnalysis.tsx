import { useCallback, useEffect, useMemo, useRef, useState, type SyntheticEvent } from "react";
import { Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api, type Strategy, type StrategyAnalysisRun } from "../api/client";
import RunAnalysisOverlay from "../components/analysis/RunAnalysisOverlay";
import { ROUTES } from "../lib/routes";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import {
  confidencePercent,
  DEFAULT_ANALYSIS_SORT_COLUMN,
  DEFAULT_ANALYSIS_SORT_DIRECTION,
  directionClassName,
  directionLabel,
  defaultAnalysisSortDirection,
  executionOutcomeClassName,
  executionOutcomeLabel,
  filterSummary,
  signalLabel,
  sortAnalysisRunsForTable,
  type AnalysisSortColumn,
  type AnalysisSortDirection,
} from "../lib/strategyAnalysis";
import { TIMEFRAME_LABELS, type Timeframe } from "../lib/strategyParams";

const POLL_INTERVAL_MS = 15_000;
const RUN_LIMIT = 100;

const DIRECTION_FILTERS = [
  { value: "all", label: "All directions" },
  { value: "long", label: "Long" },
  { value: "short", label: "Short" },
  { value: "none", label: "None" },
] as const;

const SORTABLE_COLUMNS: { key: AnalysisSortColumn; label: string }[] = [
  { key: "time", label: "Time" },
  { key: "strategy", label: "Strategy" },
  { key: "pair", label: "Pair" },
  { key: "timeframe", label: "TF" },
  { key: "direction", label: "Direction" },
  { key: "confidence", label: "Confidence" },
  { key: "signal", label: "Signal" },
  { key: "filters", label: "Filters" },
  { key: "outcome", label: "Outcome" },
];

type AnalysisTableSort = {
  column: AnalysisSortColumn;
  direction: AnalysisSortDirection;
};

const INITIAL_TABLE_SORT: AnalysisTableSort = {
  column: DEFAULT_ANALYSIS_SORT_COLUMN,
  direction: DEFAULT_ANALYSIS_SORT_DIRECTION,
};

function timeframeLabel(timeframe: string): string {
  return TIMEFRAME_LABELS[timeframe as Timeframe] ?? timeframe;
}

function SortableAnalysisHeader({
  column,
  label,
  sortColumn,
  sortDirection,
  onSort,
}: {
  column: AnalysisSortColumn;
  label: string;
  sortColumn: AnalysisSortColumn;
  sortDirection: AnalysisSortDirection;
  onSort: (column: AnalysisSortColumn) => void;
}) {
  const isActive = sortColumn === column;
  return (
    <th scope="col">
      <button
        type="button"
        className={[
          "trades-table-sort-btn",
          isActive ? "trades-table-sort-btn--active" : undefined,
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={() => onSort(column)}
        aria-sort={
          isActive ? (sortDirection === "asc" ? "ascending" : "descending") : "none"
        }
      >
        <span>{label}</span>
        <span className="trades-table-sort-indicator" aria-hidden="true">
          {isActive ? (sortDirection === "asc" ? "↑" : "↓") : "↕"}
        </span>
      </button>
    </th>
  );
}

export default function StrategyAnalysis() {
  const navigate = useNavigate();
  const { formatInstant } = useGeneralSettings();
  const [runs, setRuns] = useState<StrategyAnalysisRun[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [pairQuery, setPairQuery] = useState("");
  const [directionFilter, setDirectionFilter] = useState("all");
  const [tableSort, setTableSort] = useState<AnalysisTableSort>(INITIAL_TABLE_SORT);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [runOverlayOpen, setRunOverlayOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);

  const loadRuns = useCallback(async () => {
    const params: { limit: number; strategy_id?: string; pair?: string } = {
      limit: RUN_LIMIT,
    };
    if (strategyFilter !== "all") {
      params.strategy_id = strategyFilter;
    }
    const trimmedPair = pairQuery.trim();
    if (trimmedPair) {
      params.pair = trimmedPair;
    }
    const data = await api.listStrategyAnalysisRuns(params);
    setRuns(data.runs);
  }, [strategyFilter, pairQuery]);

  const handleSortColumn = useCallback((column: AnalysisSortColumn) => {
    setTableSort((current) => {
      if (current.column === column) {
        return {
          column,
          direction: current.direction === "asc" ? "desc" : "asc",
        };
      }
      return {
        column,
        direction: defaultAnalysisSortDirection(column),
      };
    });
  }, []);

  useEffect(() => {
    api
      .listStrategies()
      .then((data) => setStrategies(data.strategies))
      .catch(() => setStrategies([]));
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        await loadRuns();
        if (!cancelled) setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load analysis runs");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const interval = window.setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [loadRuns]);

  const filtered = useMemo(() => {
    if (directionFilter === "all") return runs;
    if (directionFilter === "none") {
      return runs.filter((run) => run.direction == null);
    }
    return runs.filter((run) => run.direction === directionFilter);
  }, [runs, directionFilter]);

  const sortedRuns = useMemo(
    () =>
      sortAnalysisRunsForTable(filtered, {
        sortColumn: tableSort.column,
        sortDirection: tableSort.direction,
      }),
    [filtered, tableSort],
  );

  const runIds = useMemo(() => sortedRuns.map((run) => run.id), [sortedRuns]);
  const selectedVisibleCount = useMemo(
    () => runIds.filter((id) => selectedIds.has(id)).length,
    [runIds, selectedIds],
  );
  const allRunsSelected = runIds.length > 0 && selectedVisibleCount === runIds.length;
  const someRunsSelected =
    selectedVisibleCount > 0 && selectedVisibleCount < runIds.length;
  const hasSelection = selectedVisibleCount > 0;

  const toggleSelected = useCallback((runId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(runId)) {
        next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
  }, []);

  const toggleSelectAllRuns = useCallback(() => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allRunsSelected) {
        for (const id of runIds) {
          next.delete(id);
        }
      } else {
        for (const id of runIds) {
          next.add(id);
        }
      }
      return next;
    });
  }, [allRunsSelected, runIds]);

  useEffect(() => {
    const checkbox = selectAllRef.current;
    if (!checkbox) return;
    checkbox.indeterminate = someRunsSelected;
    checkbox.checked = allRunsSelected;
  }, [allRunsSelected, someRunsSelected]);

  useEffect(() => {
    setSelectedIds((current) => {
      const visible = new Set(runIds);
      const next = new Set([...current].filter((id) => visible.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [runIds]);

  function openRun(run: StrategyAnalysisRun) {
    navigate(ROUTES.research.analysisRun(run.id));
  }

  function stopRowActivation(event: SyntheticEvent) {
    event.stopPropagation();
  }

  async function confirmDelete() {
    const ids = runIds.filter((id) => selectedIds.has(id));
    if (ids.length === 0) return;

    setDeleting(true);
    setDeleteError(null);
    try {
      const results = await Promise.allSettled(
        ids.map((id) => api.deleteStrategyAnalysisRun(id)),
      );
      const failed = results.filter((result) => result.status === "rejected").length;

      if (failed > 0) {
        setDeleteError(
          failed === ids.length
            ? "Could not delete selected analysis runs."
            : `${failed} of ${ids.length} analysis runs could not be deleted.`,
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
      setDeleteError(err instanceof Error ? err.message : "Failed to delete analysis runs");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="analysis-page">
      <div className="analysis-page-header">
        <div className="analysis-page-header-copy">
          <h1 className="page-title">Analysis</h1>
          <p className="settings-muted analysis-page-lead">
            History of strategy analysis runs and execution outcomes.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary analysis-run-btn"
          aria-label="Run analysis"
          onClick={() => setRunOverlayOpen(true)}
        >
          <Plus size={16} aria-hidden="true" />
          <span>Run</span>
        </button>
      </div>

      <div className="settings-panel">
        <div className="analysis-toolbar-filters">
          <div className="research-select-wrap analysis-filter-select">
            <select
              className="research-select"
              value={strategyFilter}
              onChange={(event) => setStrategyFilter(event.target.value)}
              aria-label="Filter by strategy"
            >
              <option value="all">All strategies</option>
              {strategies.map((strategy) => (
                <option key={strategy.id} value={strategy.id}>
                  {strategy.name}
                </option>
              ))}
            </select>
          </div>
          <input
            type="search"
            className="research-search"
            placeholder="Filter by pair…"
            value={pairQuery}
            onChange={(event) => setPairQuery(event.target.value)}
            aria-label="Filter by pair"
          />
          <div className="research-select-wrap analysis-filter-select analysis-filter-select--compact">
            <select
              className="research-select"
              value={directionFilter}
              onChange={(event) => setDirectionFilter(event.target.value)}
              aria-label="Filter by direction"
            >
              {DIRECTION_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="btn btn-danger btn-sm analysis-delete-btn"
            disabled={!hasSelection || deleting}
            onClick={() => setDeleteConfirmOpen(true)}
          >
            {deleting
              ? "Deleting…"
              : hasSelection
                ? `Delete (${selectedVisibleCount})`
                : "Delete"}
          </button>
        </div>

        {loading && <p className="settings-muted">Loading analysis runs…</p>}
        {error && !loading && <p className="settings-error">{error}</p>}
        {deleteError && <p className="settings-error">{deleteError}</p>}
        {!loading && !error && runs.length === 0 && (
          <p className="settings-muted">No analysis runs recorded yet.</p>
        )}
        {!loading && !error && runs.length > 0 && filtered.length === 0 && (
          <p className="settings-muted">No analysis runs match your filters.</p>
        )}

        {!loading && !error && sortedRuns.length > 0 && (
          <div className="research-table-wrap">
            <table className="research-table research-table--clickable analysis-runs-table">
              <thead>
                <tr>
                  <th className="analysis-runs-table-checkbox-col" scope="col">
                    <label className="analysis-runs-table-checkbox-label">
                      <input
                        ref={selectAllRef}
                        type="checkbox"
                        className="ui-checkbox-input"
                        checked={allRunsSelected}
                        onChange={toggleSelectAllRuns}
                        aria-label="Select all visible analysis runs"
                      />
                    </label>
                  </th>
                  {SORTABLE_COLUMNS.map((column) => (
                    <SortableAnalysisHeader
                      key={column.key}
                      column={column.key}
                      label={column.label}
                      sortColumn={tableSort.column}
                      sortDirection={tableSort.direction}
                      onSort={handleSortColumn}
                    />
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedRuns.map((run) => {
                  const isSelected = selectedIds.has(run.id);
                  return (
                    <tr
                      key={run.id}
                      className={isSelected ? "analysis-runs-table-row--selected" : undefined}
                      aria-selected={isSelected}
                      onClick={() => openRun(run)}
                    >
                      <td
                        className="analysis-runs-table-checkbox-col"
                        onClick={stopRowActivation}
                      >
                        <label className="analysis-runs-table-checkbox-label">
                          <input
                            type="checkbox"
                            className="ui-checkbox-input"
                            checked={isSelected}
                            onChange={() => toggleSelected(run.id)}
                            aria-label={`Select ${run.strategy_name} ${run.pair} analysis run`}
                          />
                        </label>
                      </td>
                      <td className="settings-muted">{formatInstant(run.analyzed_at)}</td>
                      <td>{run.strategy_name}</td>
                      <td>{run.pair}</td>
                      <td className="settings-muted">{timeframeLabel(run.timeframe)}</td>
                      <td>
                        <span className={directionClassName(run.direction)}>
                          {directionLabel(run.direction)}
                        </span>
                      </td>
                      <td>{confidencePercent(run.confidence)}</td>
                      <td>{signalLabel(run)}</td>
                      <td className="settings-muted">{filterSummary(run)}</td>
                      <td>
                        <span className={executionOutcomeClassName(run)}>
                          {executionOutcomeLabel(run)}
                        </span>
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
          onClick={() => !deleting && setDeleteConfirmOpen(false)}
        >
          <div
            className="confirm-dialog"
            role="alertdialog"
            aria-labelledby="delete-analysis-title"
            aria-describedby="delete-analysis-message"
            onClick={stopRowActivation}
          >
            <h4 id="delete-analysis-title">
              Delete {selectedVisibleCount === 1 ? "analysis run" : "analysis runs"}?
            </h4>
            <p id="delete-analysis-message">
              This will permanently delete{" "}
              <strong>
                {selectedVisibleCount} analysis run{selectedVisibleCount === 1 ? "" : "s"}
              </strong>
              .
            </p>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={deleting}
                onClick={() => setDeleteConfirmOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={deleting}
                onClick={() => void confirmDelete()}
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {runOverlayOpen && (
        <RunAnalysisOverlay
          onClose={() => setRunOverlayOpen(false)}
          onRunComplete={(runId) => {
            void loadRuns().catch(() => undefined);
            navigate(ROUTES.research.analysisRun(runId));
          }}
        />
      )}
    </div>
  );
}
