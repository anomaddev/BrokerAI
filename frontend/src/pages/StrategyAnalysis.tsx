import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import RunAnalysisOverlay from "../components/analysis/RunAnalysisOverlay";
import AnalysisFilterMultiSelect from "../components/analysis/AnalysisFilterMultiSelect";
import CandleTimeTable from "../components/analysis/CandleTimeTable";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import { ROUTES } from "../lib/routes";
import { useAnalysisPageData } from "../lib/analysis/useAnalysisPageData";
import { buildCandleTimeSummaries } from "../lib/analysis/candleTimeSummaries";
import {
  ANALYSIS_DIRECTION_FILTER_OPTIONS,
  DEFAULT_ANALYSIS_DIRECTION_FILTERS,
  analysisRunDirectionCategory,
  type AnalysisDirectionFilterValue,
} from "../lib/strategyAnalysis";

export default function StrategyAnalysis() {
  const navigate = useNavigate();
  const { formatInstant } = useGeneralSettings();
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [pairQuery, setPairQuery] = useState("");
  const [directionFilter, setDirectionFilter] = useState<Set<AnalysisDirectionFilterValue>>(
    () => new Set(DEFAULT_ANALYSIS_DIRECTION_FILTERS),
  );
  const [runOverlayOpen, setRunOverlayOpen] = useState(false);

  const {
    strategies,
    entryRuns,
    exitRuns,
    openTrades,
    loading,
    error,
    isBatchPending,
    triggerReload,
  } = useAnalysisPageData({
    strategyFilter,
    pairQuery,
  });

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

  const hasAnyRuns = allRuns.length > 0;

  return (
    <div className="analysis-page">
      <div className="analysis-page-header">
        <div className="analysis-page-header-copy">
          <h1 className="page-title">Analysis</h1>
          <p className="settings-muted analysis-page-lead">
            Entry and exit analysis grouped by candle time.
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
        </div>

        {isBatchPending ? (
          <p className="settings-muted analysis-batch-status" role="status">
            Analysis updating…
          </p>
        ) : null}

        {loading && <p className="settings-muted analysis-panel-status">Loading analysis runs…</p>}
        {error && !loading && <p className="settings-error analysis-panel-status">{error}</p>}
        {!loading && !error && !hasAnyRuns && (
          <p className="settings-muted analysis-panel-status">No analysis runs recorded yet.</p>
        )}
        {!loading && !error && hasAnyRuns && candleSummaries.length === 0 && (
          <p className="settings-muted analysis-panel-status">
            No analysis runs match your filters.
          </p>
        )}

        {!loading && !error && candleSummaries.length > 0 ? (
          <CandleTimeTable summaries={candleSummaries} />
        ) : null}
      </div>

      {runOverlayOpen && (
        <RunAnalysisOverlay
          onClose={() => setRunOverlayOpen(false)}
          onRunComplete={(runId) => {
            triggerReload();
            navigate(ROUTES.research.analysisRun(runId));
          }}
        />
      )}
    </div>
  );
}
