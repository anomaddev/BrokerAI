import { useCallback, useEffect, useMemo, useState, type SyntheticEvent } from "react";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import CandleAnalysisRunsTable from "../components/analysis/CandleAnalysisRunsTable";
import AnalysisFilterMultiSelect from "../components/analysis/AnalysisFilterMultiSelect";
import AnalysisRecencyBadge from "../components/analysis/AnalysisRecencyBadge";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import { useAnalysisPageData } from "../lib/analysis/useAnalysisPageData";
import {
  buildCandleTimeSummaries,
  runsForCandleKey,
} from "../lib/analysis/candleTimeSummaries";
import {
  buildCandleNavKeys,
  resolveCandleNeighbors,
  resolveCurrentCandleKey,
  type CandleNavigationState,
} from "../lib/analysis/candleTimeNavigation";
import { ROUTES } from "../lib/routes";
import {
  ANALYSIS_DIRECTION_FILTER_OPTIONS,
  DEFAULT_ANALYSIS_DIRECTION_FILTERS,
  analysisRunDirectionCategory,
  type AnalysisDirectionFilterValue,
} from "../lib/strategyAnalysis";

export default function StrategyAnalysisCandleView() {
  const { candleKey: rawCandleKey } = useParams<{ candleKey: string }>();
  const candleKey = rawCandleKey ? decodeURIComponent(rawCandleKey) : "";
  const navigate = useNavigate();
  const location = useLocation();
  const navigationState = location.state as CandleNavigationState | null;
  const { formatInstant } = useGeneralSettings();

  const [strategyFilter, setStrategyFilter] = useState("all");
  const [pairQuery, setPairQuery] = useState("");
  const [directionFilter, setDirectionFilter] = useState<Set<AnalysisDirectionFilterValue>>(
    () => new Set(DEFAULT_ANALYSIS_DIRECTION_FILTERS),
  );
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [navCandleKeys, setNavCandleKeys] = useState<string[]>(
    () => navigationState?.candleKeys ?? [],
  );

  const {
    strategies,
    entryRuns,
    setEntryRuns,
    exitRuns,
    setExitRuns,
    openTrades,
    loading,
    error,
    isBatchPending,
  } = useAnalysisPageData({
    strategyFilter,
    pairQuery,
  });

  useEffect(() => {
    if (navigationState?.candleKeys?.length) {
      setNavCandleKeys(navigationState.candleKeys);
    }
  }, [navigationState]);

  const strategiesById = useMemo(
    () => new Map(strategies.map((strategy) => [strategy.id, strategy])),
    [strategies],
  );

  const filteredEntryRuns = useMemo(() => {
    let next = entryRuns;

    if (directionFilter.size > 0) {
      next = next.filter((run) => directionFilter.has(analysisRunDirectionCategory(run)));
    } else {
      next = [];
    }

    return next;
  }, [entryRuns, directionFilter]);

  const allRuns = useMemo(
    () => [...filteredEntryRuns, ...exitRuns],
    [filteredEntryRuns, exitRuns],
  );

  const candleSummaries = useMemo(
    () =>
      buildCandleTimeSummaries(allRuns, strategiesById, formatInstant, {
        openTrades,
        exitRuns,
      }),
    [allRuns, strategiesById, formatInstant, openTrades, exitRuns],
  );

  useEffect(() => {
    if (navCandleKeys.length > 0 || candleSummaries.length === 0) {
      return;
    }
    setNavCandleKeys(buildCandleNavKeys(candleSummaries));
  }, [navCandleKeys.length, candleSummaries]);

  const candleKeys = navCandleKeys.length > 0
    ? navCandleKeys
    : buildCandleNavKeys(candleSummaries);

  const currentSummary = useMemo(
    () => candleSummaries.find((summary) => summary.key === candleKey) ?? null,
    [candleSummaries, candleKey],
  );

  const candleRuns = useMemo(
    () => runsForCandleKey(allRuns, candleKey),
    [allRuns, candleKey],
  );

  const neighbors = useMemo(
    () => (candleKey ? resolveCandleNeighbors(candleKeys, candleKey) : null),
    [candleKeys, candleKey],
  );

  const currentCandleKey = useMemo(
    () => resolveCurrentCandleKey(candleSummaries),
    [candleSummaries],
  );

  const selectedVisibleCount = useMemo(
    () => candleRuns.filter((run) => selectedIds.has(run.id)).length,
    [candleRuns, selectedIds],
  );
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

  useEffect(() => {
    const visible = new Set(candleRuns.map((run) => run.id));
    setSelectedIds((current) => {
      const next = new Set([...current].filter((id) => visible.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [candleRuns]);

  function navigateToCandle(targetKey: string) {
    navigate(ROUTES.research.analysisCandle(targetKey), {
      state: { candleKeys } satisfies CandleNavigationState,
    });
  }

  function stopDialogActivation(event: SyntheticEvent) {
    event.stopPropagation();
  }

  async function confirmDelete() {
    const ids = [...selectedIds];
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
        setEntryRuns((current) => current.filter((run) => !deletedIds.has(run.id)));
        setExitRuns((current) => current.filter((run) => !deletedIds.has(run.id)));
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

  const showCurrentBadge = currentSummary?.isCurrentBar ?? false;

  return (
    <div className="analysis-candle-view">
      <header className="analysis-run-view-header">
        <Link to={ROUTES.research.analysis} className="research-back-link">
          <ArrowLeft size={16} strokeWidth={1.75} />
          Back to analysis
        </Link>

        <div className="analysis-run-view-title-row">
          <div className="analysis-run-view-title-block">
            <h1 className="page-title analysis-run-view-title">
              <span className="analysis-run-view-title-text">
                Candle {currentSummary?.label ?? candleKey}
              </span>
              {showCurrentBadge ? <AnalysisRecencyBadge recency="current" /> : null}
            </h1>
            <p className="settings-muted analysis-run-view-subtitle">
              {currentSummary
                ? `${currentSummary.runCount} run${currentSummary.runCount === 1 ? "" : "s"}`
                : "Loading runs…"}
              {currentSummary && currentSummary.exitMonitorTradeCount > 0
                ? ` · ${currentSummary.exitMonitorTradeCount} exit monitor`
                : ""}
            </p>
          </div>
          <div className="analysis-run-view-actions">
            <div className="analysis-run-view-nav">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={!neighbors?.previousKey}
                onClick={() => neighbors?.previousKey && navigateToCandle(neighbors.previousKey)}
                aria-label="Previous candle time"
              >
                <ChevronLeft size={14} aria-hidden="true" />
                Previous
              </button>
              {neighbors && neighbors.index >= 0 ? (
                <span className="settings-muted analysis-run-view-nav-position">
                  {neighbors.index + 1} of {neighbors.total}
                </span>
              ) : null}
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={!neighbors?.nextKey}
                onClick={() => neighbors?.nextKey && navigateToCandle(neighbors.nextKey)}
                aria-label="Next candle time"
              >
                Next
                <ChevronRight size={14} aria-hidden="true" />
              </button>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={!currentCandleKey || currentCandleKey === candleKey}
              onClick={() => currentCandleKey && navigateToCandle(currentCandleKey)}
            >
              Jump to Current
            </button>
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
        </div>
      </header>

      <div className="settings-panel settings-panel--analysis analysis-candle-view-panel">
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
        </div>

        {isBatchPending ? (
          <p className="settings-muted analysis-batch-status" role="status">
            Analysis updating…
          </p>
        ) : null}

        {loading && <p className="settings-muted analysis-panel-status">Loading analysis runs…</p>}
        {error && !loading && <p className="settings-error analysis-panel-status">{error}</p>}
        {deleteError && <p className="settings-error analysis-panel-status">{deleteError}</p>}
        {!loading && !error && candleRuns.length === 0 && (
          <p className="settings-muted analysis-panel-status">
            {candleSummaries.length > 0
              ? "No analysis runs for this candle time."
              : "No analysis runs recorded yet."}
          </p>
        )}

        {!loading && !error && candleRuns.length > 0 ? (
          <CandleAnalysisRunsTable
            runs={candleRuns}
            strategies={strategies}
            selectedIds={selectedIds}
            onToggleSelected={toggleSelected}
            candleKey={candleKey}
            candleKeys={candleKeys}
          />
        ) : null}
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
            onClick={stopDialogActivation}
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
    </div>
  );
}
