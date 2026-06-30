import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { api, type StrategyAnalysisRun } from "../api/client";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import {
  confidencePercent,
  directionClassName,
  directionLabel,
  executionOutcomeClassName,
  executionOutcomeLabel,
  exploreHref,
  filterDetails,
  gateReasonLabel,
  signalLabel,
} from "../lib/strategyAnalysis";
import { TIMEFRAME_LABELS, type Timeframe } from "../lib/strategyParams";

function timeframeLabel(timeframe: string): string {
  return TIMEFRAME_LABELS[timeframe as Timeframe] ?? timeframe;
}

function formatValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  return String(value);
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="analysis-detail-row">
      <dt className="analysis-detail-label">{label}</dt>
      <dd className="analysis-detail-value">{value}</dd>
    </div>
  );
}

export default function StrategyAnalysisRunView() {
  const { runId } = useParams<{ runId: string }>();
  const { formatInstant } = useGeneralSettings();
  const [run, setRun] = useState<StrategyAnalysisRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const filters = run ? filterDetails(run) : [];

  return (
    <div>
      <div className="research-view-header">
        <Link to="/trading/analysis" className="research-back-link">
          <ArrowLeft size={16} strokeWidth={1.75} />
          Back to live analysis
        </Link>
      </div>

      {loading && <p className="settings-muted">Loading analysis run…</p>}
      {error && !loading && <p className="settings-error">{error}</p>}

      {run && !loading && !error && (
        <>
          <h1 className="page-title" style={{ marginBottom: "0.25rem" }}>
            {run.strategy_name} · {run.pair}
          </h1>
          <p className="settings-muted" style={{ marginBottom: "1.5rem" }}>
            {timeframeLabel(run.timeframe)}
            {run.candle_time ? ` · Candle ${formatInstant(run.candle_time)}` : ""}
            {run.analyzed_at ? ` · Analyzed ${formatInstant(run.analyzed_at)}` : ""}
          </p>

          <div className="analysis-detail-grid">
            <section className="settings-panel">
              <h2 className="settings-subtitle">Summary</h2>
              <dl className="analysis-detail-list">
                <DetailRow label="Strategy" value={run.strategy_name} />
                <DetailRow label="Pair" value={run.pair} />
                <DetailRow label="Timeframe" value={timeframeLabel(run.timeframe)} />
                <DetailRow
                  label="Direction"
                  value={directionLabel(run.direction)}
                />
                <DetailRow label="Confidence" value={confidencePercent(run.confidence)} />
                <DetailRow label="Min candles" value={String(run.min_candles)} />
                <DetailRow label="Run type" value={run.run_type} />
                <DetailRow
                  label="Outcome"
                  value={executionOutcomeLabel(run)}
                />
              </dl>
              <div className="analysis-detail-actions">
                <Link
                  to={`/trading/strategies/${encodeURIComponent(run.strategy_id)}/edit`}
                  className="btn btn-secondary btn-sm"
                >
                  Edit strategy
                </Link>
                <Link to={exploreHref(run)} className="btn btn-secondary btn-sm">
                  <ExternalLink size={14} aria-hidden="true" />
                  Open in Explore
                </Link>
              </div>
            </section>

            <section className="settings-panel">
              <h2 className="settings-subtitle">Signal</h2>
              <dl className="analysis-detail-list">
                <DetailRow label="Signal type" value={run.signal_type.replace(/_/g, " ")} />
                <DetailRow label="Signal" value={signalLabel(run)} />
                <DetailRow
                  label="Crossover time"
                  value={
                    run.metadata.crossover_time
                      ? formatInstant(String(run.metadata.crossover_time))
                      : "—"
                  }
                />
                <DetailRow
                  label="ADX"
                  value={formatValue(run.metadata.adx)}
                />
                <DetailRow
                  label="Confirmation"
                  value={formatValue(run.metadata.confirmation)}
                />
              </dl>
            </section>

            <section className="settings-panel">
              <h2 className="settings-subtitle">Filters</h2>
              {filters.length === 0 && (
                <p className="settings-muted">No filter data recorded.</p>
              )}
              {filters.length > 0 && (
                <ul className="analysis-filter-list">
                  {filters.map((filter) => (
                    <li key={filter.id} className="analysis-filter-item">
                      <div className="analysis-filter-header">
                        <span className="analysis-filter-id">{filter.id}</span>
                        <span
                          className={`research-tag ${
                            filter.passed ? "analysis-tag--pass" : "analysis-tag--fail"
                          }`}
                        >
                          {filter.passed ? "Pass" : "Fail"}
                        </span>
                      </div>
                      <dl className="analysis-detail-list analysis-detail-list--compact">
                        {Object.entries(filter.values).map(([key, value]) => (
                          <DetailRow key={key} label={key.replace(/_/g, " ")} value={formatValue(value)} />
                        ))}
                      </dl>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="settings-panel">
              <h2 className="settings-subtitle">Execution</h2>
              {!run.execution && (
                <p className="settings-muted">Executor has not processed this run yet.</p>
              )}
              {run.execution && (
                <>
                  <dl className="analysis-detail-list">
                    <DetailRow
                      label="Processed at"
                      value={formatInstant(run.execution.processed_at)}
                    />
                    <DetailRow
                      label="Gates passed"
                      value={run.execution.gates_passed ? "Yes" : "No"}
                    />
                    <DetailRow
                      label="Priority winner"
                      value={run.execution.priority_winner ? "Yes" : "No"}
                    />
                    <DetailRow
                      label="Intent queued"
                      value={run.execution.intent_queued ? "Yes" : "No"}
                    />
                    <DetailRow
                      label="Outcome"
                      value={executionOutcomeLabel(run)}
                    />
                  </dl>
                  {run.execution.gate_reasons.length > 0 && (
                    <div className="analysis-gate-reasons">
                      <h3 className="analysis-section-heading">Gate reasons</h3>
                      <ul>
                        {run.execution.gate_reasons.map((reason) => (
                          <li key={reason}>
                            <span className={executionOutcomeClassName(run)}>
                              {gateReasonLabel(reason)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {run.execution.intent && (
                    <div className="analysis-intent-block">
                      <h3 className="analysis-section-heading">Trade intent</h3>
                      <dl className="analysis-detail-list analysis-detail-list--compact">
                        <DetailRow label="Direction" value={run.execution.intent.direction} />
                        <DetailRow
                          label="Entry"
                          value={formatValue(run.execution.intent.entry_price)}
                        />
                        <DetailRow
                          label="Stop loss"
                          value={formatValue(run.execution.intent.stop_loss)}
                        />
                        <DetailRow
                          label="Take profit"
                          value={formatValue(run.execution.intent.take_profit)}
                        />
                        <DetailRow
                          label="Confidence"
                          value={confidencePercent(run.execution.intent.confidence)}
                        />
                      </dl>
                    </div>
                  )}
                </>
              )}
            </section>
          </div>

          <p className="settings-muted" style={{ marginTop: "1rem" }}>
            <span className={directionClassName(run.direction)}>
              {directionLabel(run.direction)}
            </span>
            {" · "}
            Run ID {run.id}
          </p>
        </>
      )}
    </div>
  );
}
