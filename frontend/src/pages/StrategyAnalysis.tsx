import { useCallback, useEffect, useMemo, useRef, useState, type SyntheticEvent } from "react";
import { Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api, type Strategy, type StrategyAnalysisRun } from "../api/client";
import RunAnalysisOverlay from "../components/analysis/RunAnalysisOverlay";
import AnalysisFilterMultiSelect from "../components/analysis/AnalysisFilterMultiSelect";
import AnalysisRecencyBadge from "../components/analysis/AnalysisRecencyBadge";
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
  runSourceClassName,
  runSourceLabel,
  signalLabel,
  sortAnalysisRunsForTable,
  analysisRunDirectionCategory,
  ANALYSIS_DIRECTION_FILTER_OPTIONS,
  DEFAULT_ANALYSIS_DIRECTION_FILTERS,
  type AnalysisDirectionFilterValue,
  type AnalysisSortColumn,
  type AnalysisSortDirection,
} from "../lib/strategyAnalysis";
import { TIMEFRAME_LABELS, type Timeframe } from "../lib/strategyParams";
import {
  analysisRunRecency,
  buildStaleAnalysisRunIds,
} from "../lib/analysis/analysisRunRecency";
import {
  buildAnalysisRunNavIds,
  type AnalysisRunNavigationState,
} from "../lib/analysis/analysisRunNavigation";

const POLL_INTERVAL_MS = 15_000;
const MAX_FETCH_LIMIT = 200;
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200] as const;
const DEFAULT_PAGE_SIZE = 25;

type PageSize = (typeof PAGE_SIZE_OPTIONS)[number];

const SORTABLE_COLUMNS: { key: AnalysisSortColumn; label: string }[] = [
  { key: "time", label: "Time" },
  { key: "source", label: "Source" },
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
  const [directionFilter, setDirectionFilter] = useState<Set<AnalysisDirectionFilterValue>>(
    () => new Set(DEFAULT_ANALYSIS_DIRECTION_FILTERS),
  );
  const [tableSort, setTableSort] = useState<AnalysisTableSort>(INITIAL_TABLE_SORT);
  const [pageSize, setPageSize] = useState<PageSize>(DEFAULT_PAGE_SIZE);
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [runOverlayOpen, setRunOverlayOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);

  const loadRuns = useCallback(async () => {
    const params: { limit: number; strategy_id?: string; pair?: string } = {
      limit: MAX_FETCH_LIMIT,
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

  const staleRunIds = useMemo(() => buildStaleAnalysisRunIds(runs), [runs]);

  const filtered = useMemo(() => {
    let next = runs;

    if (directionFilter.size > 0) {
      next = next.filter((run) => directionFilter.has(analysisRunDirectionCategory(run)));
    } else {
      next = [];
    }

    return next;
  }, [runs, directionFilter]);

  const sortedRuns = useMemo(
    () =>
      sortAnalysisRunsForTable(filtered, {
        sortColumn: tableSort.column,
        sortDirection: tableSort.direction,
      }),
    [filtered, tableSort],
  );

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(sortedRuns.length / pageSize)),
    [sortedRuns.length, pageSize],
  );

  const currentPage = Math.min(page, totalPages);

  const paginatedRuns = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedRuns.slice(start, start + pageSize);
  }, [sortedRuns, currentPage, pageSize]);

  const pageRangeStart = sortedRuns.length === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const pageRangeEnd = Math.min(currentPage * pageSize, sortedRuns.length);

  useEffect(() => {
    setPage(1);
  }, [strategyFilter, pairQuery, directionFilter, tableSort, pageSize]);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const runIds = useMemo(() => paginatedRuns.map((run) => run.id), [paginatedRuns]);
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
    const runIds = buildAnalysisRunNavIds(sortedRuns, {
      sortColumn: tableSort.column,
      sortDirection: tableSort.direction,
    });
    navigate(ROUTES.research.analysisRun(run.id), {
      state: { runIds } satisfies AnalysisRunNavigationState,
    });
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

      <div className="settings-panel settings-panel--analysis">
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
          <div className="analysis-filter-select analysis-filter-select--compact">
            <AnalysisFilterMultiSelect
              label="Directions"
              ariaLabel="Filter by direction"
              options={ANALYSIS_DIRECTION_FILTER_OPTIONS}
              value={directionFilter}
              onChange={setDirectionFilter}
            />
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

        {loading && <p className="settings-muted analysis-panel-status">Loading analysis runs…</p>}
        {error && !loading && <p className="settings-error analysis-panel-status">{error}</p>}
        {deleteError && <p className="settings-error analysis-panel-status">{deleteError}</p>}
        {!loading && !error && runs.length === 0 && (
          <p className="settings-muted analysis-panel-status">No analysis runs recorded yet.</p>
        )}
        {!loading && !error && runs.length > 0 && filtered.length === 0 && (
          <p className="settings-muted analysis-panel-status">No analysis runs match your filters.</p>
        )}

        {!loading && !error && sortedRuns.length > 0 && (
          <div className="analysis-table-section">
            <div className="research-table-wrap analysis-table-wrap">
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
                          aria-label="Select all analysis runs on this page"
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
                  {paginatedRuns.map((run) => {
                  const isSelected = selectedIds.has(run.id);
                  const recency = analysisRunRecency(run, staleRunIds);
                  const rowClassName = [
                    isSelected ? "analysis-runs-table-row--selected" : undefined,
                    recency === "current" ? "analysis-runs-table-row--current-bar" : undefined,
                    recency === "stale" ? "analysis-runs-table-row--stale-bar" : undefined,
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <tr
                      key={run.id}
                      className={rowClassName || undefined}
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
                      <td className="settings-muted">
                        <span className="analysis-run-time-cell">
                          <span>{formatInstant(run.analyzed_at, "compact")}</span>
                          <AnalysisRecencyBadge recency={recency} />
                        </span>
                      </td>
                      <td>
                        <span className={runSourceClassName(run)}>{runSourceLabel(run)}</span>
                      </td>
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

            <div className="analysis-pagination">
              <div className="analysis-pagination__size">
                <label className="analysis-pagination__size-label" htmlFor="analysis-page-size">
                  Rows per page
                </label>
                <div className="research-select-wrap analysis-pagination__size-select">
                  <select
                    id="analysis-page-size"
                    className="research-select"
                    value={pageSize}
                    onChange={(event) =>
                      setPageSize(Number(event.target.value) as PageSize)
                    }
                    aria-label="Rows per page"
                  >
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <p className="settings-muted analysis-pagination__summary">
                Showing {pageRangeStart}–{pageRangeEnd} of {sortedRuns.length}
                {runs.length >= MAX_FETCH_LIMIT ? ` (latest ${MAX_FETCH_LIMIT})` : ""}
              </p>

              <div className="analysis-pagination__controls">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={currentPage <= 1}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                >
                  Previous
                </button>
                <span className="analysis-pagination__page">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={currentPage >= totalPages}
                  onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                >
                  Next
                </button>
              </div>
            </div>
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
