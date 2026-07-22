import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ROUTES } from "../../lib/routes";
import type { StrategyParamsV1 } from "../../lib/strategyParams";
import { TIMEFRAME_LABELS } from "../../lib/strategyParams";
import { findSignalCatalogEntry } from "../../lib/strategyParams/catalog";
import { api, type AssetClass } from "../../api/client";
import StrategyOverlay from "./StrategyOverlay";
import { ASSET_PILL_LABELS } from "./StrategyAssetPills";
import {
  ALL_ASSET_CLASSES,
  countSelectedInstruments,
  hasInstrumentSelection,
  specificSymbols,
  type StrategyInstrumentSelection,
} from "../../lib/strategies/instruments";

type ReviewRow = {
  label: string;
  value: string;
  warn?: boolean;
};

type SaveStrategyOverlayProps = {
  mode: "create" | "edit";
  strategyId?: string;
  presetId: string;
  presetLabel?: string;
  /** Strategy name from the builder inline title. */
  strategyName: string;
  /** Notes from the builder footer. */
  notes?: string;
  params: StrategyParamsV1;
  instrumentSelection: StrategyInstrumentSelection;
  /** Optional multi-signal logic expression from the builder. */
  signalLogic?: string;
  initialEnabled?: boolean;
  onClose: () => void;
};

function assetClassChips(selection: StrategyInstrumentSelection): {
  assetClass: AssetClass;
  label: string;
  count: number;
}[] {
  const chips: { assetClass: AssetClass; label: string; count: number }[] = [];
  for (const assetClass of ALL_ASSET_CLASSES) {
    const symbols = selection[assetClass];
    if (!symbols?.length) continue;
    chips.push({
      assetClass,
      label: ASSET_PILL_LABELS[assetClass],
      count: specificSymbols(symbols).length,
    });
  }
  return chips;
}

function buildReviewRows(
  params: StrategyParamsV1,
  signalLogic: string | undefined,
): ReviewRow[] {
  const emaLabels = Object.values(params.indicators ?? {})
    .filter((spec) => spec.type === "ema")
    .map((spec) => `EMA ${spec.period}`);
  const signalEntry = findSignalCatalogEntry(params.signal.type);
  const signalLabel = signalEntry?.label ?? params.signal.type;
  const signalDetail =
    params.signal.type === "ema_crossover"
      ? `${signalLabel} · ${params.signal.direction}`
      : signalLabel;

  const filterLabels = params.filters
    .filter((filter) => filter.enabled !== false)
    .map((filter) => filter.type.toUpperCase());

  const slOn = params.exits.stop_loss.enabled !== false;
  const tpOn = params.exits.take_profit.enabled !== false;
  const riskParts = [`${params.risk.risk_per_trade_pct}% risk`];
  if (slOn) riskParts.push("SL on");
  if (tpOn) riskParts.push("TP on");
  if (!slOn && !tpOn) riskParts.push("No SL/TP");

  return [
    {
      label: "Timeframe",
      value: params.timeframe
        ? `${TIMEFRAME_LABELS[params.timeframe]} · ${params.min_candles ?? "—"} bars`
        : "Not set",
      warn: !params.timeframe,
    },
    {
      label: "Indicators",
      value: emaLabels.length > 0 ? emaLabels.join(", ") : "None",
    },
    {
      label: "Signal",
      value: signalLogic?.trim() || signalDetail,
      warn: !params.signal?.type,
    },
    {
      label: "Filters",
      value: filterLabels.length > 0 ? filterLabels.join(", ") : "None",
    },
    {
      label: "Risk",
      value: riskParts.join(" · "),
    },
    {
      label: "Execution",
      value: `${params.execution.min_confidence}% confidence · ${params.risk.max_trades_per_day}/day`,
    },
  ];
}

export default function SaveStrategyOverlay({
  mode,
  strategyId,
  presetId,
  presetLabel,
  strategyName,
  notes = "",
  params,
  instrumentSelection,
  signalLogic,
  initialEnabled = false,
  onClose,
}: SaveStrategyOverlayProps) {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedName = strategyName.trim();
  const sessions = params.execution?.sessions ?? [];
  const chips = useMemo(() => assetClassChips(instrumentSelection), [instrumentSelection]);
  const reviewRows = useMemo(
    () => buildReviewRows(params, signalLogic),
    [params, signalLogic],
  );
  const instrumentCount = countSelectedInstruments(instrumentSelection);

  const missing: string[] = [];
  if (!trimmedName) missing.push("Strategy name");
  if (!params.timeframe) missing.push("Timeframe");
  if (presetId === "ai_strategy") {
    if (instrumentCount !== 1) missing.push("Exactly one instrument");
  } else if (!hasInstrumentSelection(instrumentSelection)) {
    missing.push("Assets");
  }
  if (sessions.length === 0) missing.push("Trading sessions");

  const canSubmit = missing.length === 0 && !submitting;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const payloadParams: StrategyParamsV1 = {
        ...params,
        execution: {
          ...params.execution,
          sessions: [...sessions],
        },
      };

      const description = notes.trim();
      let savedId = strategyId;
      if (mode === "edit" && strategyId) {
        await api.updateStrategy(strategyId, {
          name: trimmedName,
          description,
          params: payloadParams,
          instrument_selection: instrumentSelection,
          enabled: initialEnabled,
        });
      } else {
        const created = await api.createStrategy({
          name: trimmedName,
          description,
          preset_id: presetId,
          params: payloadParams,
          instrument_selection: instrumentSelection,
          // AI Strategies start enabled so startup + shadow warm-up can run.
          // Manual templates stay disabled until the user turns them on.
          enabled: presetId === "ai_strategy",
        });
        savedId = created.id;
      }
      onClose();
      if (presetId === "ai_strategy" && savedId) {
        navigate(ROUTES.research.aiStrategyView(savedId));
      } else {
        navigate(ROUTES.research.strategies);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save strategy");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <StrategyOverlay onClose={onClose} wide titleId="save-strategy-overlay-title">
      <div className="model-overlay-body strategy-review">
        <p className="strategy-review-eyebrow">
          {mode === "edit" ? "Review changes" : "Review strategy"}
        </p>
        <h4 className="model-overlay-title strategy-review-title" id="save-strategy-overlay-title">
          {trimmedName || "Untitled strategy"}
        </h4>
        <p className="model-overlay-desc strategy-review-subtitle">
          {[presetLabel, params.timeframe ? TIMEFRAME_LABELS[params.timeframe] : null]
            .filter(Boolean)
            .join(" · ") || "Confirm the builder selections, then save."}
        </p>

        <div className="strategy-review-summary-grid">
          <section className="strategy-review-card">
            <div className="strategy-review-card-header">
              <h5 className="strategy-review-card-title">Assets</h5>
              <span className="strategy-review-card-meta">
                {instrumentCount > 0 ? `${instrumentCount} selected` : "Required"}
              </span>
            </div>
            {chips.length > 0 ? (
              <div className="strategy-review-asset-chips">
                {chips.map((chip) => (
                  <span
                    key={chip.assetClass}
                    className={`strategy-asset-pill strategy-asset-pill--${chip.assetClass} strategy-asset-pill--selected strategy-review-asset-chip`}
                  >
                    <span className="strategy-asset-pill-toggle">
                      <span>{chip.label}</span>
                      <span className="strategy-asset-pill-count">{chip.count}</span>
                    </span>
                  </span>
                ))}
              </div>
            ) : (
              <p className="param-helper param-helper--warn">
                Select assets from the pills in the builder header.
              </p>
            )}
          </section>

          <section className="strategy-review-card">
            <div className="strategy-review-card-header">
              <h5 className="strategy-review-card-title">Sessions</h5>
              <span className="strategy-review-card-meta">
                {sessions.length > 0 ? `${sessions.length} selected` : "Required"}
              </span>
            </div>
            {sessions.length > 0 ? (
              <div className="strategy-review-session-chips">
                {sessions.map((session) => (
                  <span key={session} className="strategy-review-session-chip">
                    {session}
                  </span>
                ))}
              </div>
            ) : (
              <p className="param-helper param-helper--warn">
                Choose sessions under Execution in the builder.
              </p>
            )}
          </section>
        </div>

        <section className="strategy-review-card strategy-review-card--rows">
          <div className="strategy-review-card-header">
            <h5 className="strategy-review-card-title">Components</h5>
          </div>
          <dl className="strategy-review-rows">
            {reviewRows.map((row) => (
              <div key={row.label} className="strategy-review-row">
                <dt>{row.label}</dt>
                <dd className={row.warn ? "strategy-review-row-value--warn" : undefined}>
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>
        </section>

        {notes.trim() ? (
          <section className="strategy-review-card">
            <div className="strategy-review-card-header">
              <h5 className="strategy-review-card-title">Notes</h5>
            </div>
            <p className="strategy-review-notes">{notes.trim()}</p>
          </section>
        ) : null}

        {missing.length > 0 ? (
          <p className="param-helper param-helper--warn strategy-review-missing">
            Still needed: {missing.join(", ")}.
          </p>
        ) : (
          <p className="strategy-review-ready">
            {mode === "edit"
              ? "Everything looks ready to save."
              : "Everything looks ready to create."}
          </p>
        )}
      </div>

      <div className="model-overlay-footer">
        {error && <p className="settings-error model-overlay-feedback">{error}</p>}
        <div className="confirm-actions model-overlay-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            Back to builder
          </button>
          <div className="model-overlay-actions-primary">
            <button type="button" className="btn" onClick={handleSubmit} disabled={!canSubmit}>
              {submitting
                ? mode === "edit"
                  ? "Saving…"
                  : "Creating…"
                : mode === "edit"
                  ? "Save changes"
                  : "Create strategy"}
            </button>
          </div>
        </div>
      </div>
    </StrategyOverlay>
  );
}
