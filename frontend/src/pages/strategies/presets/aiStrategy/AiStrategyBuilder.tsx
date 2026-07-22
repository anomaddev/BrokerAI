import { useCallback, useEffect, useMemo, useState } from "react";
import { Brain } from "lucide-react";
import { api } from "../../../../api/client";
import DiscardStrategyChangesDialog from "../../../../components/strategies/DiscardStrategyChangesDialog";
import SaveStrategyOverlay from "../../../../components/strategies/SaveStrategyOverlay";
import StrategyBuilderFooter from "../../../../components/strategies/StrategyBuilderFooter";
import StrategyBuilderHeader from "../../../../components/strategies/StrategyBuilderHeader";
import StrategyVersionHistoryOverlay from "../../../../components/strategies/StrategyVersionHistoryOverlay";
import ParameterCard from "../../../../components/strategies/params/ParameterCard";
import ParamToggleRow from "../../../../components/strategies/params/ParamToggleRow";
import TimeframeSelect from "../../../../components/strategies/params/TimeframeSelect";
import LiveSlider from "../../../../components/strategies/params/LiveSlider";
import { useGeneralSettings } from "../../../../hooks/useGeneralSettings";
import { useStrategyBuilderExit } from "../../../../hooks/useStrategyBuilderExit";
import { formatAppInstant } from "../../../../lib/formatTime";
import { normalizeVersionSnapshotForBuilder } from "../../../../lib/strategyBuilder/loadVersion";
import { clampStrategyTitle } from "../../../../lib/strategyBuilder/components";
import { strategyBuilderDirtySnapshot } from "../../../../lib/strategyBuilder/unsavedChanges";
import {
  emptyInstrumentSelection,
  hasInstrumentSelection,
  type StrategyInstrumentSelection,
} from "../../../../lib/strategies/instruments";
import {
  TIMEFRAME_LABELS,
  TIMEFRAME_OPTIONS,
  formatCandleLookback,
  type StrategyParamsV1,
  type Timeframe,
} from "../../../../lib/strategyParams";
import { STRATEGY_PRESETS } from "../../presets";
import { aiStrategyParamsToV1, v1ToAiStrategyParams } from "./apiParams";
import {
  AI_LOOKBACK_MAX,
  AI_LOOKBACK_MIN,
  DEFAULT_AI_STRATEGY_PARAMS,
  type AiStrategyParams,
} from "./defaults";

const ACCORDION_KEY = "brokerai-ai-strategy-accordion-v1";
const DEFAULT_SECTIONS = {
  market: true,
  guidance: true,
  lookback: true,
};

type SectionKey = keyof typeof DEFAULT_SECTIONS;

function loadSections(): Record<SectionKey, boolean> {
  try {
    const raw = localStorage.getItem(ACCORDION_KEY);
    if (raw) return { ...DEFAULT_SECTIONS, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return DEFAULT_SECTIONS;
}

type AiStrategyBuilderProps = {
  initialParams?: AiStrategyParams;
  initialParamsV1?: StrategyParamsV1;
  editStrategyId?: string;
  editName?: string;
  editDescription?: string;
  editInstrumentSelection?: StrategyInstrumentSelection;
  editEnabled?: boolean;
};

function createInitialState(
  initialParams: AiStrategyParams | undefined,
  editName: string | undefined,
  editDescription: string | undefined,
  editInstrumentSelection: StrategyInstrumentSelection | undefined,
) {
  const params = { ...(initialParams ?? DEFAULT_AI_STRATEGY_PARAMS) };
  const title = clampStrategyTitle(editName ?? "AI Strategy");
  const notes = editDescription ?? "";
  const instrumentSelection = editInstrumentSelection ?? emptyInstrumentSelection();
  return {
    params,
    title,
    notes,
    instrumentSelection,
    baselineSnapshot: strategyBuilderDirtySnapshot({
      title,
      notes,
      instrumentSelection,
      components: [],
      params: params as unknown as Record<string, unknown>,
    }),
  };
}

export default function AiStrategyBuilder({
  initialParams,
  initialParamsV1: _initialParamsV1,
  editStrategyId,
  editName,
  editDescription,
  editInstrumentSelection,
  editEnabled,
}: AiStrategyBuilderProps) {
  const [initial] = useState(() =>
    createInitialState(initialParams, editName, editDescription, editInstrumentSelection),
  );
  const [params, setParams] = useState<AiStrategyParams>(() => initial.params);
  const [title, setTitle] = useState(() => initial.title);
  const [notes, setNotes] = useState(() => initial.notes);
  const [notesExpanded, setNotesExpanded] = useState(false);
  const [instrumentSelection, setInstrumentSelection] = useState<StrategyInstrumentSelection>(
    () => initial.instrumentSelection,
  );
  const [sections, setSections] = useState(loadSections);
  const [panelOpen, setPanelOpen] = useState(false);
  const [saveOverlayOpen, setSaveOverlayOpen] = useState(false);
  const [historyOverlayOpen, setHistoryOverlayOpen] = useState(false);
  const [enabled] = useState(() => Boolean(editEnabled));
  const [versionBannerAt, setVersionBannerAt] = useState<string | null>(null);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);
  const { timeOptions } = useGeneralSettings();

  const preset = STRATEGY_PRESETS.find((p) => p.id === "ai_strategy");
  const supportedAssetClasses = preset?.assetClasses ?? (["forex"] as const);
  const isEditMode = Boolean(editStrategyId);
  const isDirty =
    strategyBuilderDirtySnapshot({
      title,
      notes,
      instrumentSelection,
      components: [],
      params: params as unknown as Record<string, unknown>,
    }) !== initial.baselineSnapshot;
  const { requestClose, discardConfirmOpen, confirmDiscard, cancelDiscard } =
    useStrategyBuilderExit(isDirty);

  const toggleSection = useCallback((key: SectionKey) => {
    setSections((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        localStorage.setItem(ACCORDION_KEY, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const update = useCallback(<K extends keyof AiStrategyParams>(key: K, value: AiStrategyParams[K]) => {
    setParams((prev) => ({ ...prev, [key]: value }));
  }, []);

  const setLookback = useCallback((value: number) => {
    setParams((prev) => ({
      ...prev,
      minCandles: value,
      maxContextBars: value,
    }));
  }, []);

  const handleLoadVersion = useCallback(
    async (versionId: string) => {
      if (!editStrategyId) return;
      const detail = await api.getStrategyVersion(editStrategyId, versionId);
      const normalized = normalizeVersionSnapshotForBuilder(detail.snapshot);
      const builderParams = v1ToAiStrategyParams(normalized.params);
      setParams(builderParams);
      setTitle(normalized.title);
      setNotes(normalized.notes);
      setInstrumentSelection(normalized.instrumentSelection);
      setCurrentVersion(detail.version);
      setVersionBannerAt(detail.created_at);
      setHistoryOverlayOpen(false);
    },
    [editStrategyId],
  );

  useEffect(() => {
    if (!editStrategyId) {
      setCurrentVersion(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const response = await api.listStrategyVersions(editStrategyId, {
          limit: 1,
          offset: 0,
        });
        if (!cancelled) {
          setCurrentVersion(response.versions[0]?.version ?? null);
        }
      } catch {
        if (!cancelled) setCurrentVersion(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [editStrategyId]);

  const lookbackInvalid =
    params.maxContextBars < AI_LOOKBACK_MIN || params.maxContextBars > AI_LOOKBACK_MAX;
  const canSave =
    Boolean(params.timeframe) &&
    params.sessions.length > 0 &&
    title.trim().length > 0 &&
    hasInstrumentSelection(instrumentSelection) &&
    !lookbackInvalid;

  const saveParams = useMemo(() => aiStrategyParamsToV1(params), [params]);

  return (
    <div className="strategy-builder">
      <div className="strategy-builder-body">
        {versionBannerAt ? (
          <div className="strategy-builder-version-banner" role="status">
            Viewing version from {formatAppInstant(versionBannerAt, timeOptions, "short")} — Save to
            keep these changes.
            <button
              type="button"
              className="strategy-builder-version-banner-dismiss"
              onClick={() => setVersionBannerAt(null)}
              aria-label="Dismiss version banner"
            >
              Dismiss
            </button>
          </div>
        ) : null}

        <StrategyBuilderHeader
          title={title}
          onTitleChange={setTitle}
          instrumentSelection={instrumentSelection}
          onInstrumentSelectionChange={setInstrumentSelection}
          supportedAssetClasses={[...supportedAssetClasses]}
          onClose={requestClose}
          currentVersion={currentVersion}
        />

        <div className="strategy-builder-main">
          <div className="strategy-builder-chart-area">
            <div className="strategy-builder-ai-intro">
              <div className="strategy-builder-ai-intro-icon" aria-hidden="true">
                <Brain size={28} />
              </div>
              <h3 className="strategy-builder-ai-intro-title">AI Strategy</h3>
              <p className="strategy-builder-ai-intro-body">
                Model-derived entries guided by daily reports and weekly briefs. New strategies
                begin in a shadow warm-up period; promote to live from the Strategies list when
                ready.
              </p>
              <p className="strategy-builder-ai-intro-note settings-muted">
                Name and description are set when you save. Forex instruments only in this release.
              </p>
            </div>
          </div>

          <aside
            className={`strategy-builder-panel${panelOpen ? " strategy-builder-panel--open" : ""}`}
          >
            <div className="strategy-builder-panel-handle" aria-hidden="true" />
            <div className="strategy-builder-panel-header strategy-builder-panel-header--in-panel">
              <h2 className="strategy-builder-panel-title">Parameters</h2>
              {currentVersion != null ? (
                <span className="strategy-builder-current-version" title="Currently saved version">
                  v{currentVersion}
                </span>
              ) : null}
            </div>
            <div className="strategy-builder-panel-scroll">
              <ParameterCard
                title="Market"
                required
                expanded={sections.market}
                onToggle={() => toggleSection("market")}
              >
                <TimeframeSelect
                  label="Timeframe"
                  required
                  value={params.timeframe}
                  options={TIMEFRAME_OPTIONS}
                  onChange={(value: Timeframe) => update("timeframe", value)}
                />
                <p className="param-helper">
                  Pick forex pairs with the asset pills above. Other asset classes are not available
                  for AI Strategy yet.
                </p>
              </ParameterCard>

              <ParameterCard
                title="Guidance"
                expanded={sections.guidance}
                onToggle={() => toggleSection("guidance")}
              >
                <ParamToggleRow
                  label="Use daily report"
                  checked={params.useDailyReport}
                  onChange={(checked) => update("useDailyReport", checked)}
                />
                <ParamToggleRow
                  label="Use weekly brief"
                  checked={params.useWeeklyBrief}
                  onChange={(checked) => update("useWeeklyBrief", checked)}
                />
                <ParamToggleRow
                  label="Use weekly debrief"
                  checked={params.useWeeklyDebrief}
                  onChange={(checked) => update("useWeeklyDebrief", checked)}
                />
                <div className="param-control param-control--readonly">
                  <span className="param-control-label">LLM mode</span>
                  <span className="param-control-value param-control-value--locked">Off</span>
                </div>
                <p className="param-helper">
                  Live LLM calls stay off in this release. Guidance toggles still select which
                  research inputs the model may use later.
                </p>
              </ParameterCard>

              <ParameterCard
                title="Lookback"
                required
                expanded={sections.lookback}
                onToggle={() => toggleSection("lookback")}
                badge={lookbackInvalid ? "!" : undefined}
              >
                <LiveSlider
                  id="ai-lookback-bars"
                  label="Context lookback (bars)"
                  value={params.maxContextBars}
                  min={AI_LOOKBACK_MIN}
                  max={AI_LOOKBACK_MAX}
                  step={1}
                  invalid={lookbackInvalid}
                  onChange={setLookback}
                />
                <p className="param-helper">
                  Sets both minimum candles and AI context bars ({AI_LOOKBACK_MIN}–
                  {AI_LOOKBACK_MAX}).
                  {params.maxContextBars > 0
                    ? ` About ${formatCandleLookback(params.timeframe, params.maxContextBars)} at ${TIMEFRAME_LABELS[params.timeframe]}.`
                    : null}
                </p>
                <p className="param-helper">
                  Warm-up: new AI strategies shadow-trade for several forex trading days (from asset
                  settings) before you can promote them to live.
                </p>
              </ParameterCard>
            </div>
          </aside>
        </div>

        <StrategyBuilderFooter
          notes={notes}
          onNotesChange={setNotes}
          notesExpanded={notesExpanded}
          onNotesExpandedChange={setNotesExpanded}
          canSave={canSave}
          titleEmpty={title.trim().length === 0}
          onSave={() => setSaveOverlayOpen(true)}
          onCancel={requestClose}
          onHistory={isEditMode ? () => setHistoryOverlayOpen(true) : undefined}
        />
      </div>

      <button
        type="button"
        className="strategy-builder-panel-fab"
        onClick={() => setPanelOpen((v) => !v)}
        aria-expanded={panelOpen}
      >
        Parameters
      </button>

      <DiscardStrategyChangesDialog
        open={discardConfirmOpen}
        onCancel={cancelDiscard}
        onDiscard={confirmDiscard}
      />

      {historyOverlayOpen && editStrategyId ? (
        <StrategyVersionHistoryOverlay
          strategyId={editStrategyId}
          isDirty={isDirty}
          onClose={() => setHistoryOverlayOpen(false)}
          onLoadVersion={handleLoadVersion}
        />
      ) : null}

      {saveOverlayOpen && preset ? (
        <SaveStrategyOverlay
          mode={isEditMode ? "edit" : "create"}
          strategyId={editStrategyId}
          presetId="ai_strategy"
          presetLabel={preset.label}
          strategyName={title}
          notes={notes}
          params={saveParams}
          instrumentSelection={instrumentSelection}
          initialEnabled={enabled}
          onClose={() => setSaveOverlayOpen(false)}
        />
      ) : null}
    </div>
  );
}
