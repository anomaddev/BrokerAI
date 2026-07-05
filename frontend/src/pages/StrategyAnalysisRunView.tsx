import { useEffect, useMemo, useState, type SyntheticEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Trash2 } from "lucide-react";
import {
  api,
  type CandleBar,
  type Strategy,
  type StrategyAnalysisRun,
} from "../api/client";
import AnalysisRunDetailPanel from "../components/analysis/AnalysisRunDetailPanel";
import ExploreCandleChart from "../components/explore/ExploreCandleChart";
import { ROUTES } from "../lib/routes";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import {
  analysisChartTimeframe,
  buildAnalysisCandleWindow,
} from "../lib/analysis/analysisCandleWindow";
import {
  analysisRunCrossoverSignal,
  type SignalLookback,
} from "../lib/analysis/analysisRunChartSignals";
import { parseAppInstant } from "../lib/formatTime";
import { decomposeStrategyToLayers } from "../lib/chart/chartOverlayState";
import { directionClassName, directionLabel } from "../lib/strategyAnalysis";
import { TIMEFRAME_LABELS, type Timeframe } from "../lib/strategyParams";

function timeframeLabel(timeframe: string): string {
  return TIMEFRAME_LABELS[timeframe as Timeframe] ?? timeframe;
}

export default function StrategyAnalysisRunView() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { formatInstant } = useGeneralSettings();
  const [run, setRun] = useState<StrategyAnalysisRun | null>(null);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [candles, setCandles] = useState<CandleBar[]>([]);
  const [candleWindowBounds, setCandleWindowBounds] = useState<{
    since: string;
    until: string;
    displaySince: string;
    displayUntil: string;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [candlesLoading, setCandlesLoading] = useState(false);
  const [strategyLoading, setStrategyLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candlesError, setCandlesError] = useState<string | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      setError("No analysis run specified");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .getStrategyAnalysisRun(runId)
      .then((data) => setRun(data))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load analysis run"),
      )
      .finally(() => setLoading(false));
  }, [runId]);

  useEffect(() => {
    if (!run?.strategy_id) {
      setStrategy(null);
      setStrategyLoading(false);
      return;
    }

    let cancelled = false;
    setStrategyLoading(true);
    void api
      .getStrategy(run.strategy_id)
      .then((loaded) => {
        if (!cancelled) setStrategy(loaded);
      })
      .catch(() => {
        if (!cancelled) setStrategy(null);
      })
      .finally(() => {
        if (!cancelled) setStrategyLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [run?.strategy_id]);

  useEffect(() => {
    if (!runId || !run) {
      setCandles([]);
      setCandleWindowBounds(null);
      setCandlesLoading(false);
      setCandlesError(null);
      return;
    }

    let cancelled = false;
    setCandlesLoading(true);
    setCandlesError(null);
    setCandleWindowBounds(null);

    void api
      .getStrategyAnalysisRunCandles(runId)
      .then((response) => {
        if (cancelled) return;
        setCandles(response.candles);
        setCandleWindowBounds({
          since: response.since,
          until: response.until,
          displaySince: response.display_since,
          displayUntil: response.display_until,
        });
        if (response.candles.length === 0) {
          setCandlesError("No candle data for this analysis window.");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setCandles([]);
          setCandlesError(err instanceof Error ? err.message : "Failed to load chart data");
        }
      })
      .finally(() => {
        if (!cancelled) setCandlesLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [runId, run]);

  const timeframe = useMemo(
    () => analysisChartTimeframe(run?.timeframe),
    [run?.timeframe],
  );

  const overlayItems = useMemo(
    () => (strategy ? decomposeStrategyToLayers(strategy) : []),
    [strategy],
  );

  const focusWindow = useMemo(
    () => (run ? buildAnalysisCandleWindow(run, candleWindowBounds) : null),
    [run, candleWindowBounds],
  );

  const pinnedSignals = useMemo(() => {
    if (!run) return [];
    const signal = analysisRunCrossoverSignal(run);
    return signal ? [signal] : [];
  }, [run]);

  const signalLookback = useMemo((): SignalLookback | null => {
    if (!run) return null;
    const rawTime = run.candle_time ?? run.analyzed_at;
    if (rawTime == null) return null;
    const date = parseAppInstant(String(rawTime));
    if (!date) return null;
    return {
      anchorTime: Math.floor(date.getTime() / 1000),
      bars: 10,
    };
  }, [run]);

  const chartLoading = candlesLoading || (Boolean(run?.strategy_id) && strategyLoading);

  function stopDialogActivation(event: SyntheticEvent) {
    event.stopPropagation();
  }

  async function confirmDelete() {
    if (!runId || deleting) return;

    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteStrategyAnalysisRun(runId);
      setDeleteConfirmOpen(false);
      navigate(ROUTES.research.analysis);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete analysis run");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="analysis-run-view">
      <header className="analysis-run-view-header">
        <Link to={ROUTES.research.analysis} className="research-back-link">
          <ArrowLeft size={16} strokeWidth={1.75} />
          Back to analysis
        </Link>

        {run && !loading && !error && (
          <div className="analysis-run-view-title-row">
            <div className="analysis-run-view-title-block">
              <h1 className="page-title analysis-run-view-title">
                {run.strategy_name} · {run.pair}
              </h1>
              <p className="settings-muted analysis-run-view-subtitle">
                <span className={directionClassName(run.direction)}>
                  {directionLabel(run.direction)}
                </span>
                {" · "}
                {timeframeLabel(run.timeframe)}
                {run.candle_time ? ` · Candle ${formatInstant(run.candle_time)}` : ""}
                {run.analyzed_at ? ` · Analyzed ${formatInstant(run.analyzed_at)}` : ""}
              </p>
            </div>
            <button
              type="button"
              className="btn btn-danger btn-sm analysis-run-delete-btn"
              disabled={deleting}
              onClick={() => {
                setDeleteError(null);
                setDeleteConfirmOpen(true);
              }}
            >
              <Trash2 size={14} aria-hidden="true" />
              Delete
            </button>
          </div>
        )}
      </header>

      {loading && <p className="settings-muted analysis-run-view-status">Loading analysis run…</p>}
      {error && !loading && <p className="settings-error analysis-run-view-status">{error}</p>}

      {run && !loading && !error && (
        <div className="analysis-run-detail-layout">
          <div
            className={`analysis-run-chart-col${
              chartLoading ? " analysis-run-chart-col--loading" : ""
            }`}
          >
            {chartLoading ? (
              <div
                className="analysis-run-chart-loading explore-chart-status explore-chart-status--loading"
                role="status"
                aria-live="polite"
              >
                Loading chart…
              </div>
            ) : null}
            <ExploreCandleChart
              symbol={run.pair}
              timeframe={timeframe}
              candles={candles}
              loading={candlesLoading}
              error={candlesError}
              overlayItems={overlayItems}
              focusWindow={focusWindow}
              pinnedSignals={pinnedSignals}
              signalLookback={signalLookback}
            />
          </div>
          <aside className="analysis-run-panel-col">
            <AnalysisRunDetailPanel run={run} />
          </aside>
        </div>
      )}

      {deleteConfirmOpen && run && (
        <div
          className="confirm-overlay"
          role="presentation"
          onClick={() => !deleting && setDeleteConfirmOpen(false)}
        >
          <div
            className="confirm-dialog"
            role="alertdialog"
            aria-labelledby="delete-analysis-run-title"
            aria-describedby="delete-analysis-run-message"
            onClick={stopDialogActivation}
          >
            <h4 id="delete-analysis-run-title">Delete analysis run?</h4>
            <p id="delete-analysis-run-message">
              This will permanently delete the{" "}
              <strong>
                {run.strategy_name} · {run.pair}
              </strong>{" "}
              analysis run from {formatInstant(run.analyzed_at)}.
            </p>
            {deleteError && <p className="settings-error">{deleteError}</p>}
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
