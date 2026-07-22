import { useCallback, useEffect, useMemo, useState } from "react";
import { Brain } from "lucide-react";
import { api, type AiModel } from "../../../../api/client";
import DiscardStrategyChangesDialog from "../../../../components/strategies/DiscardStrategyChangesDialog";
import SaveStrategyOverlay from "../../../../components/strategies/SaveStrategyOverlay";
import StrategyBuilderFooter from "../../../../components/strategies/StrategyBuilderFooter";
import StrategyBuilderHeader from "../../../../components/strategies/StrategyBuilderHeader";
import StrategyVersionHistoryOverlay from "../../../../components/strategies/StrategyVersionHistoryOverlay";
import ParameterCard from "../../../../components/strategies/params/ParameterCard";
import ParamHelpTip from "../../../../components/strategies/params/ParamHelpTip";
import ParamSelect from "../../../../components/strategies/params/ParamSelect";
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
import {
  catalogSelectionKey,
  parseCatalogSelectionKey,
  providerLabel,
} from "../../../settings/modelProviders";
import { STRATEGY_PRESETS } from "../../presets";
import { aiStrategyParamsToV1, v1ToAiStrategyParams } from "./apiParams";
import {
  AI_LOOKBACK_MAX,
  AI_LOOKBACK_MIN,
  AI_LOOKBACK_STEP,
  DEFAULT_AI_STRATEGY_PARAMS,
  LLM_MODE_OPTIONS,
  type AiStrategyParams,
} from "./defaults";

const ACCORDION_KEY = "brokerai-ai-strategy-accordion-v1";
const DEFAULT_SECTIONS = {
  market: true,
  guidance: true,
  model: true,
  lookback: true,
};

type SectionKey = keyof typeof DEFAULT_SECTIONS;

type CatalogOption = {
  key: string;
  sourceId: string;
  modelName: string;
  label: string;
};

const AI_HELP = {
  timeframe: {
    label: "Timeframe",
    title: "Timeframe",
    body: "Candle interval used for AI context and decision timing. Forex pairs are selected with the asset pills above.",
  },
  useDailyReport: {
    label: "Use daily report",
    title: "Use daily report",
    body: "Include the latest daily research report as directional bias only — it does not place trades by itself.",
  },
  useWeeklyBrief: {
    label: "Use weekly brief",
    title: "Use weekly brief",
    body: "Include the weekly brief summary so the model sees the broader weekly outlook.",
  },
  useWeeklyDebrief: {
    label: "Use weekly debrief",
    title: "Use weekly debrief",
    body: "Include the weekly debrief so the model can weigh what worked or failed last week.",
  },
  learnEnabled: {
    label: "Learn from outcomes",
    title: "Learn from outcomes",
    body: "When on, trade outcomes feed memory digests and daily compiled-playbook improve runs (Settings → Backtesting).",
  },
  decisionModel: {
    label: "Decision model",
    title: "Decision model",
    body: "Choose a model from an enabled Settings → Models provider. This is the LLM used for live AI Strategy decisions.",
  },
  llmMode: {
    label: "LLM mode",
    title: "LLM mode",
    body: "Off skips LLM calls. Interval throttles spend (default 240 minutes). On signal change and Manual call more often when enabled.",
  },
  lookback: {
    label: "Context lookback",
    title: "Context lookback (bars)",
    body: "How many recent candles are sent as context and required before the strategy runs. Values step by 5. Higher values add history but cost more tokens.",
  },
} as const;

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
  const params = { ...DEFAULT_AI_STRATEGY_PARAMS, ...(initialParams ?? {}) };
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

async function loadCatalogOptions(sources: AiModel[]): Promise<CatalogOption[]> {
  const enabledSources = sources.filter((m) => m.enabled);
  const options: CatalogOption[] = [];
  await Promise.all(
    enabledSources.map(async (source) => {
      const pushFallback = () => {
        const fallback = source.default_model_name || source.model_name;
        if (!fallback) return;
        options.push({
          key: catalogSelectionKey(source.id, fallback),
          sourceId: source.id,
          modelName: fallback,
          label: `${providerLabel(source.type)} · ${fallback}`,
        });
      };
      try {
        const response = await api.listAvailableModels(source.id);
        const listed = response.models ?? [];
        if (listed.length === 0) {
          pushFallback();
          return;
        }
        for (const model of listed) {
          const name = model.id || model.name;
          if (!name) continue;
          options.push({
            key: catalogSelectionKey(source.id, name),
            sourceId: source.id,
            modelName: name,
            label: `${providerLabel(source.type)} · ${model.name || name}`,
          });
        }
      } catch {
        pushFallback();
      }
    }),
  );
  options.sort((a, b) => a.label.localeCompare(b.label));
  return options;
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
  const [catalog, setCatalog] = useState<CatalogOption[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const { timeOptions } = useGeneralSettings();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setCatalogLoading(true);
      try {
        const data = await api.listModels();
        const sources = data.models || [];
        const options = await loadCatalogOptions(sources);
        if (!cancelled) setCatalog(options);
      } catch {
        if (!cancelled) setCatalog([]);
      } finally {
        if (!cancelled) setCatalogLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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
    const snapped =
      AI_LOOKBACK_MIN +
      Math.round((value - AI_LOOKBACK_MIN) / AI_LOOKBACK_STEP) * AI_LOOKBACK_STEP;
    const next = Math.min(AI_LOOKBACK_MAX, Math.max(AI_LOOKBACK_MIN, snapped));
    setParams((prev) => ({
      ...prev,
      minCandles: next,
      maxContextBars: next,
    }));
  }, []);

  const selectedModelKey = useMemo(() => {
    if (params.modelId && params.modelName) {
      return catalogSelectionKey(params.modelId, params.modelName);
    }
    return "";
  }, [params.modelId, params.modelName]);

  const modelOptions = useMemo(() => {
    const options = [{ value: "", label: catalogLoading ? "Loading models…" : "Select a model…" }];
    const seen = new Set<string>([""]);
    for (const item of catalog) {
      if (seen.has(item.key)) continue;
      seen.add(item.key);
      options.push({ value: item.key, label: item.label });
    }
    // Keep a saved selection visible even if the catalog call missed it.
    if (selectedModelKey && !seen.has(selectedModelKey) && params.modelId && params.modelName) {
      options.push({
        value: selectedModelKey,
        label: params.modelName,
      });
    }
    return options;
  }, [catalog, catalogLoading, params.modelId, params.modelName, selectedModelKey]);

  const handleModelChange = useCallback(
    (value: string) => {
      const parsed = parseCatalogSelectionKey(value);
      if (!parsed) {
        setParams((prev) => ({ ...prev, modelId: null, modelName: null }));
        return;
      }
      setParams((prev) => ({
        ...prev,
        modelId: parsed.sourceId,
        modelName: parsed.modelName,
      }));
    },
    [],
  );

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
    params.maxContextBars < AI_LOOKBACK_MIN ||
    params.maxContextBars > AI_LOOKBACK_MAX ||
    params.maxContextBars % AI_LOOKBACK_STEP !== 0;
  const canSave =
    Boolean(params.timeframe) &&
    params.sessions.length > 0 &&
    title.trim().length > 0 &&
    hasInstrumentSelection(instrumentSelection) &&
    !lookbackInvalid;

  const saveParams = useMemo(() => aiStrategyParamsToV1(params), [params]);
  const modelSelectionIncomplete =
    params.llmMode !== "off" && (!params.modelId || !params.modelName);

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
                  labelHelp={
                    <ParamHelpTip
                      label={AI_HELP.timeframe.label}
                      title={AI_HELP.timeframe.title}
                      body={AI_HELP.timeframe.body}
                    />
                  }
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
                  labelHelp={
                    <ParamHelpTip
                      label={AI_HELP.useDailyReport.label}
                      title={AI_HELP.useDailyReport.title}
                      body={AI_HELP.useDailyReport.body}
                    />
                  }
                  onChange={(checked) => update("useDailyReport", checked)}
                />
                <ParamToggleRow
                  label="Use weekly brief"
                  checked={params.useWeeklyBrief}
                  labelHelp={
                    <ParamHelpTip
                      label={AI_HELP.useWeeklyBrief.label}
                      title={AI_HELP.useWeeklyBrief.title}
                      body={AI_HELP.useWeeklyBrief.body}
                    />
                  }
                  onChange={(checked) => update("useWeeklyBrief", checked)}
                />
                <ParamToggleRow
                  label="Use weekly debrief"
                  checked={params.useWeeklyDebrief}
                  labelHelp={
                    <ParamHelpTip
                      label={AI_HELP.useWeeklyDebrief.label}
                      title={AI_HELP.useWeeklyDebrief.title}
                      body={AI_HELP.useWeeklyDebrief.body}
                    />
                  }
                  onChange={(checked) => update("useWeeklyDebrief", checked)}
                />
                <ParamToggleRow
                  label="Learn from outcomes"
                  checked={params.learnEnabled}
                  labelHelp={
                    <ParamHelpTip
                      label={AI_HELP.learnEnabled.label}
                      title={AI_HELP.learnEnabled.title}
                      body={AI_HELP.learnEnabled.body}
                    />
                  }
                  onChange={(checked) => update("learnEnabled", checked)}
                />
                <p className="param-helper">
                  Research inputs are bias only. Learning feeds memory digests and daily
                  compiled-playbook improve runs (Settings → Backtesting).
                </p>
              </ParameterCard>

              <ParameterCard
                title="Model"
                expanded={sections.model ?? true}
                onToggle={() => toggleSection("model")}
              >
                <ParamSelect
                  id="ai-decision-model"
                  label="Decision model"
                  value={selectedModelKey}
                  options={modelOptions}
                  labelHelp={
                    <ParamHelpTip
                      label={AI_HELP.decisionModel.label}
                      title={AI_HELP.decisionModel.title}
                      body={AI_HELP.decisionModel.body}
                    />
                  }
                  onChange={handleModelChange}
                />
                <ParamSelect
                  id="ai-llm-mode"
                  label="LLM mode"
                  value={params.llmMode}
                  options={LLM_MODE_OPTIONS}
                  labelHelp={
                    <ParamHelpTip
                      label={AI_HELP.llmMode.label}
                      title={AI_HELP.llmMode.title}
                      body={AI_HELP.llmMode.body}
                    />
                  }
                  onChange={(value) => update("llmMode", value)}
                />
                <p className="param-helper">
                  Keep mode Off during warm-up unless you intentionally want spend-gated
                  decisions. Interval mode throttles calls (default 240 minutes) and respects
                  daily / per-symbol caps.
                </p>
                {!catalogLoading && catalog.length === 0 ? (
                  <p className="param-helper param-helper--warn">
                    No models available. Connect and enable a provider under Settings → Models.
                  </p>
                ) : null}
                {modelSelectionIncomplete ? (
                  <p className="param-helper param-helper--warn">
                    Select a model from an enabled Settings → Models provider before live LLM
                    decisions can run.
                  </p>
                ) : null}
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
                  step={AI_LOOKBACK_STEP}
                  invalid={lookbackInvalid}
                  labelHelp={
                    <ParamHelpTip
                      label={AI_HELP.lookback.label}
                      title={AI_HELP.lookback.title}
                      body={AI_HELP.lookback.body}
                    />
                  }
                  onChange={setLookback}
                />
                <p className="param-helper">
                  Sets both minimum candles and AI context bars ({AI_LOOKBACK_MIN}–
                  {AI_LOOKBACK_MAX}, steps of {AI_LOOKBACK_STEP}).
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
