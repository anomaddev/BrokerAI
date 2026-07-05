import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { AssetClass } from "../../api/client";
import { ROUTES } from "../../lib/routes";
import type { StrategyParamsV1 } from "../../lib/strategyParams";
import { TIMEFRAME_LABELS } from "../../lib/strategyParams";
import { api } from "../../api/client";
import CreateStrategySessionFields from "./CreateStrategySessionFields";
import StrategyOverlay from "./StrategyOverlay";
import StrategyAssetTreePicker from "./StrategyAssetTreePicker";
import type { StrategyTemplatePill } from "../../lib/strategies/types";
import {
  emptyInstrumentSelection,
  hasInstrumentSelection,
  type StrategyInstrumentSelection,
} from "../../lib/strategies/instruments";

type SaveStrategyOverlayProps = {
  mode: "create" | "edit";
  strategyId?: string;
  presetId: string;
  templateName: string;
  templateDescription: string;
  supportedAssetClasses: AssetClass[];
  templatePills?: StrategyTemplatePill[];
  params: StrategyParamsV1;
  sessionDefaults: string[];
  sessionOptions: readonly string[];
  initialInstrumentSelection?: StrategyInstrumentSelection;
  initialEnabled?: boolean;
  onClose: () => void;
};

const DESCRIPTION_MAX = 160;

export default function SaveStrategyOverlay({
  mode,
  strategyId,
  presetId,
  templateName,
  templateDescription,
  supportedAssetClasses,
  templatePills = [],
  params,
  sessionDefaults,
  sessionOptions,
  initialInstrumentSelection,
  initialEnabled = false,
  onClose,
}: SaveStrategyOverlayProps) {
  const navigate = useNavigate();
  const [name, setName] = useState(templateName);
  const [description, setDescription] = useState(templateDescription.slice(0, DESCRIPTION_MAX));
  const [instrumentSelection, setInstrumentSelection] = useState<StrategyInstrumentSelection>(
    initialInstrumentSelection ?? emptyInstrumentSelection(),
  );
  const [sessions, setSessions] = useState<string[]>([...sessionDefaults]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedName = name.trim();
  const hasTimeframe = Boolean(params.timeframe);
  const canSubmit =
    trimmedName.length > 0 &&
    hasTimeframe &&
    hasInstrumentSelection(instrumentSelection) &&
    sessions.length > 0 &&
    !submitting;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const payloadParams: StrategyParamsV1 = {
        ...params,
        execution: {
          ...params.execution,
          sessions,
        },
      };

      if (mode === "edit" && strategyId) {
        await api.updateStrategy(strategyId, {
          name: trimmedName,
          description: description.trim(),
          params: payloadParams,
          instrument_selection: instrumentSelection,
          enabled: initialEnabled,
        });
      } else {
        await api.createStrategy({
          name: trimmedName,
          description: description.trim(),
          preset_id: presetId,
          params: payloadParams,
          instrument_selection: instrumentSelection,
          enabled: false,
        });
      }
      onClose();
      navigate(ROUTES.research.strategies);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save strategy");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <StrategyOverlay
      onClose={onClose}
      extraWide
      titleId="save-strategy-overlay-title"
    >
      <div className="model-overlay-body">
        <h4 className="model-overlay-title" id="save-strategy-overlay-title">
          {mode === "edit" ? "Save strategy changes" : "Create strategy"}
        </h4>
        <p className="model-overlay-desc">
          {mode === "edit"
            ? "Update the name, instruments, sessions, and saved parameters for this strategy."
            : "Name your strategy, choose a timeframe and trading sessions, and select which assets it should run on."}
        </p>

        <div className="settings-form model-overlay-form create-strategy-form">
          <div className="param-control">
            <span className="param-control-label">
              Timeframe
              <span className="param-control-required">Required</span>
            </span>
            <span className="strategy-meta-chip strategy-meta-chip--accent">
              {params.timeframe ? TIMEFRAME_LABELS[params.timeframe] : "Not set"}
            </span>
          </div>

          <label htmlFor="strategy-name">
            Strategy name
            <input
              id="strategy-name"
              type="text"
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
              autoComplete="off"
            />
          </label>

          <label htmlFor="strategy-description">
            Description
            <textarea
              id="strategy-description"
              className="create-strategy-description"
              value={description}
              maxLength={DESCRIPTION_MAX}
              rows={3}
              onChange={(e) => setDescription(e.target.value)}
            />
            <span className="create-strategy-char-count">
              {description.length}/{DESCRIPTION_MAX}
            </span>
          </label>

          <CreateStrategySessionFields
            value={sessions}
            sessionOptions={sessionOptions}
            onChange={setSessions}
          />

          <StrategyAssetTreePicker
            value={instrumentSelection}
            onChange={setInstrumentSelection}
            supportedAssetClasses={supportedAssetClasses}
            suggestedPills={templatePills}
          />
        </div>
      </div>

      <div className="model-overlay-footer">
        {error && <p className="settings-error model-overlay-feedback">{error}</p>}
        <div className="confirm-actions model-overlay-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
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
