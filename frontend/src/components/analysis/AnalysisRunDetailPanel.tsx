import { type ReactNode } from "react";
import type { StrategyAnalysisRun } from "../../api/client";
import { useGeneralSettings } from "../../hooks/useGeneralSettings";
import {
  confidencePercent,
  directionClassName,
  directionLabel,
  executionOutcomeClassName,
  executionOutcomeLabel,
  filterDetails,
  gateReasonLabel,
  isExecutorEligible,
  runSourceClassName,
  runSourceLabel,
  signalLabel,
  isApproachingSignal,
} from "../../lib/strategyAnalysis";
import { formatCandleOpenCloseLabel, resolveKnownTimeframe } from "../../lib/candleTime";
import type { AnalysisRunRecency } from "../../lib/analysis/analysisRunRecency";
import { TIMEFRAME_LABELS, type Timeframe } from "../../lib/strategyParams";
import AnalysisRecencyBadge from "./AnalysisRecencyBadge";

function timeframeLabel(timeframe: string): string {
  return TIMEFRAME_LABELS[timeframe as Timeframe] ?? timeframe;
}

function filterMetricsUseRowLayout(filterId: string): boolean {
  const normalized = filterId.trim().toLowerCase();
  return normalized === "adx" || normalized === "atr";
}

function formatFilterLabel(id: string): string {
  const labels: Record<string, string> = {
    adx: "ADX",
    atr: "ATR",
    rsi: "RSI",
    ema: "EMA",
    session: "Session",
  };
  const normalized = id.trim().toLowerCase();
  if (labels[normalized]) return labels[normalized];
  return normalized
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatMetricLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  return String(value);
}

function DetailRow({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: ReactNode;
  valueClassName?: string;
}) {
  return (
    <div className="analysis-detail-row">
      <dt className="analysis-detail-label">{label}</dt>
      <dd className={["analysis-detail-value", valueClassName].filter(Boolean).join(" ")}>
        {value}
      </dd>
    </div>
  );
}

function AnalysisDetailSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="trade-detail-section" aria-labelledby={`analysis-detail-${title}`}>
      <h3 className="trade-detail-section-title" id={`analysis-detail-${title}`}>
        {title}
      </h3>
      {children}
    </section>
  );
}

type AnalysisRunDetailPanelProps = {
  run: StrategyAnalysisRun;
  recency?: AnalysisRunRecency;
};

export default function AnalysisRunDetailPanel({ run, recency }: AnalysisRunDetailPanelProps) {
  const { formatInstant, timeOptions } = useGeneralSettings();
  const filters = filterDetails(run);
  const passedFilterCount = filters.filter((filter) => filter.passed).length;
  const approaching = isApproachingSignal(run);
  const signalCandleTime = approaching
    ? run.metadata.signal_time
    : run.metadata.crossover_time;
  const signalCandleLabel = approaching ? "Signal candle" : "Crossover candle";

  return (
    <div className="trade-detail-panel-scroll">
      <AnalysisDetailSection title="Summary">
        <dl className="analysis-detail-list">
          <DetailRow label="Strategy" value={run.strategy_name} />
          <DetailRow
            label="Source"
            value={
              <span className={runSourceClassName(run)}>{runSourceLabel(run)}</span>
            }
          />
          <DetailRow label="Pair" value={run.pair} />
          <DetailRow label="Timeframe" value={timeframeLabel(run.timeframe)} />
          {recency && recency !== "historical" ? (
            <DetailRow
              label="Candle bar"
              value={<AnalysisRecencyBadge recency={recency} />}
            />
          ) : null}
          <DetailRow
            label="Direction"
            value={
              <span className={directionClassName(run.direction)}>
                {directionLabel(run.direction)}
              </span>
            }
          />
          <DetailRow label="Confidence" value={confidencePercent(run.confidence)} />
          <DetailRow label="Min candles" value={String(run.min_candles)} />
          <DetailRow label="Outcome" value={executionOutcomeLabel(run)} />
        </dl>
      </AnalysisDetailSection>

      <AnalysisDetailSection title="Signal">
        <dl className="analysis-detail-list">
          <DetailRow label="Signal type" value={run.signal_type.replace(/_/g, " ")} />
          <DetailRow label="Signal" value={signalLabel(run)} />
          <DetailRow
            label={signalCandleLabel}
            value={
              signalCandleTime
                ? formatCandleOpenCloseLabel(
                    String(signalCandleTime),
                    resolveKnownTimeframe(run.timeframe),
                    timeOptions,
                  ) ?? "—"
                : "—"
            }
          />
          {approaching && (
            <>
              <DetailRow label="EMA gap" value={formatValue(run.metadata.ema_gap)} />
              <DetailRow label="EMA gap (ATR)" value={formatValue(run.metadata.ema_gap_atr)} />
              <DetailRow
                label="Convergence bars"
                value={formatValue(run.metadata.convergence_bars)}
              />
            </>
          )}
          <DetailRow label="ADX" value={formatValue(run.metadata.adx)} />
          <DetailRow label="Confirmation" value={formatValue(run.metadata.confirmation)} />
        </dl>
      </AnalysisDetailSection>

      <AnalysisDetailSection title="Filters">
        {filters.length === 0 && (
          <p className="settings-muted analysis-filter-empty">No filter data recorded.</p>
        )}
        {filters.length > 0 && (
          <>
            <div className="analysis-filter-summary" aria-live="polite">
              <span className="analysis-filter-summary-count">
                {passedFilterCount} of {filters.length} passed
              </span>
              <span
                className={`analysis-filter-summary-state${
                  passedFilterCount === filters.length
                    ? " analysis-filter-summary-state--pass"
                    : " analysis-filter-summary-state--fail"
                }`}
              >
                {passedFilterCount === filters.length ? "All clear" : "Blocked"}
              </span>
            </div>
            <ul className="analysis-filter-list">
              {filters.map((filter) => (
                <li
                  key={filter.id}
                  className={`analysis-filter-item${
                    filter.passed
                      ? " analysis-filter-item--pass"
                      : " analysis-filter-item--fail"
                  }`}
                >
                  <div className="analysis-filter-header">
                    <div className="analysis-filter-title-wrap">
                      <span
                        className={`analysis-filter-status-dot${
                          filter.passed
                            ? " analysis-filter-status-dot--pass"
                            : " analysis-filter-status-dot--fail"
                        }`}
                        aria-hidden="true"
                      />
                      <span className="analysis-filter-id">{formatFilterLabel(filter.id)}</span>
                    </div>
                    <span
                      className={`analysis-filter-badge${
                        filter.passed
                          ? " analysis-filter-badge--pass"
                          : " analysis-filter-badge--fail"
                      }`}
                    >
                      {filter.passed ? "Pass" : "Fail"}
                    </span>
                  </div>
                  {Object.keys(filter.values).length > 0 ? (
                    <dl
                      className={`analysis-filter-metrics${
                        filterMetricsUseRowLayout(filter.id)
                          ? " analysis-filter-metrics--row"
                          : ""
                      }`}
                    >
                      {Object.entries(filter.values).map(([key, value]) => (
                        <div key={key} className="analysis-filter-metric">
                          <dt className="analysis-filter-metric-label">
                            {formatMetricLabel(key)}
                          </dt>
                          <dd className="analysis-filter-metric-value">
                            {formatValue(value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p className="settings-muted analysis-filter-no-metrics">No metrics recorded.</p>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </AnalysisDetailSection>

      <AnalysisDetailSection title="Execution">
        {!run.execution && (
          <p className="settings-muted">
            {isExecutorEligible(run)
              ? "Executor has not processed this run yet."
              : "No trade signal — not submitted to the executor."}
          </p>
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
              <DetailRow label="Outcome" value={executionOutcomeLabel(run)} />
            </dl>
            {run.execution.gate_reasons.length > 0 && (
              <div className="analysis-gate-reasons">
                <h4 className="analysis-section-heading">Gate reasons</h4>
                <ul>
                  {run.execution.gate_reasons.map((reason) => (
                    <li key={reason}>
                      <span className={executionOutcomeClassName(run)}>
                        {gateReasonLabel(reason, run.execution?.gate_details)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {run.execution.intent && (
              <div className="analysis-intent-block">
                <h4 className="analysis-section-heading">Trade intent</h4>
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
      </AnalysisDetailSection>

      <p className="settings-muted analysis-run-panel-footer">
        <span className={directionClassName(run.direction)}>
          {directionLabel(run.direction)}
        </span>
        {" · "}
        Run ID {run.id}
      </p>
    </div>
  );
}
