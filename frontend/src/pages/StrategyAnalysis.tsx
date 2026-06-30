import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Strategy, type StrategyAnalysisRun } from "../api/client";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import {
  confidencePercent,
  directionClassName,
  directionLabel,
  executionOutcomeClassName,
  executionOutcomeLabel,
  filterSummary,
  signalLabel,
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

function timeframeLabel(timeframe: string): string {
  return TIMEFRAME_LABELS[timeframe as Timeframe] ?? timeframe;
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

  function openRun(run: StrategyAnalysisRun) {
    navigate(`/trading/analysis/${run.id}`);
  }

  return (
    <div>
      <h1 className="page-title">Live Analysis</h1>
      <p className="settings-muted" style={{ marginBottom: "1rem" }}>
        History of live candle analysis runs and execution outcomes for your strategies.
      </p>

      <div className="settings-panel">
        <div className="settings-panel-header">
          <h2 className="settings-subtitle">Analysis runs</h2>
        </div>

        <div className="research-filters">
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
          <input
            type="search"
            className="research-search"
            placeholder="Filter by pair…"
            value={pairQuery}
            onChange={(event) => setPairQuery(event.target.value)}
            aria-label="Filter by pair"
          />
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

        {loading && <p className="settings-muted">Loading analysis runs…</p>}
        {error && !loading && <p className="settings-error">{error}</p>}
        {!loading && !error && filtered.length === 0 && (
          <p className="settings-muted">No analysis runs recorded yet.</p>
        )}

        {!loading && !error && filtered.length > 0 && (
          <div className="research-table-wrap">
            <table className="research-table research-table--clickable">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Strategy</th>
                  <th>Pair</th>
                  <th>TF</th>
                  <th>Direction</th>
                  <th>Confidence</th>
                  <th>Signal</th>
                  <th>Filters</th>
                  <th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((run) => (
                  <tr key={run.id} onClick={() => openRun(run)}>
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
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
