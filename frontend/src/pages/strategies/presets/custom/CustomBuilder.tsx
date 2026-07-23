import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../../../api/client";
import DiscardStrategyChangesDialog from "../../../../components/strategies/DiscardStrategyChangesDialog";
import SaveStrategyOverlay from "../../../../components/strategies/SaveStrategyOverlay";
import StrategyBuilderFooter from "../../../../components/strategies/StrategyBuilderFooter";
import StrategyBuilderHeader from "../../../../components/strategies/StrategyBuilderHeader";
import StrategyVersionHistoryOverlay from "../../../../components/strategies/StrategyVersionHistoryOverlay";
import StrategyComponentsPanel from "../../../../components/strategies/components/StrategyComponentsPanel";
import StrategyChartShell from "../../../../components/strategies/chart/StrategyChartShell";
import { useGeneralSettings } from "../../../../hooks/useGeneralSettings";
import { formatAppInstant } from "../../../../lib/formatTime";
import { normalizeVersionSnapshotForBuilder } from "../../../../lib/strategyBuilder/loadVersion";
import {
  ExecutionSection,
  FiltersSection,
  RiskManagementSection,
  SignalRulesSection,
  type RiskManagementState,
} from "../../../../components/strategies/params/sections";
import { useStrategyBuilderExit } from "../../../../hooks/useStrategyBuilderExit";
import {
  MIN_CANDLES_SLIDER_MAX,
  MIN_CANDLES_SLIDER_MIN,
  computeBuilderMinCandles,
  roundUpMinCandles,
} from "../../../../lib/strategyParams/helpers";
import { STRATEGY_PRESETS } from "../../presets";
import { ALL_ASSET_CLASSES } from "../../strategyAssignment";
import {
  emptyInstrumentSelection,
  type StrategyInstrumentSelection,
} from "../../../../lib/strategies/instruments";
import {
  clampStrategyTitle,
  formatSignalLogicExpression,
  getEmaComponents,
  getMarketsComponent,
  getSignalComponent,
  getSignalComponents,
  hasDuplicateEmaPeriods,
  seedCustomComponents,
  updateComponent,
  type StrategyBuilderComponent,
} from "../../../../lib/strategyBuilder/components";
import {
  applyComponentsToBuilderFields,
  componentsFromParamsV1,
  emaPeriodsFromComponents,
  mergeComponentsIntoParamsV1,
} from "../../../../lib/strategyBuilder/syncParams";
import { strategyBuilderDirtySnapshot } from "../../../../lib/strategyBuilder/unsavedChanges";
import type { StrategyParamsV1 } from "../../../../lib/strategyParams";
import {
  DEFAULT_CUSTOM_BUILDER_PARAMS,
  customBuilderParamsToV1,
  v1ToCustomBuilderParams,
  type CustomBuilderParams,
} from "./defaults";

const ACCORDION_KEY = "brokerai-custom-builder-accordion-v4";
const DEFAULT_SECTIONS = {
  filters: true,
  signalRules: true,
  risk: false,
  execution: false,
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

function seedComponents(
  initialParams: CustomBuilderParams | undefined,
  initialV1: StrategyParamsV1 | undefined,
): StrategyBuilderComponent[] {
  if (initialV1) return componentsFromParamsV1(initialV1, initialParams?.minCandles ?? 200);
  if (initialParams) {
    try {
      const v1 = customBuilderParamsToV1(initialParams);
      return componentsFromParamsV1(v1, initialParams.minCandles);
    } catch {
      return seedCustomComponents(initialParams.minCandles);
    }
  }
  return seedCustomComponents();
}

type CustomBuilderProps = {
  initialParams?: CustomBuilderParams;
  initialParamsV1?: StrategyParamsV1;
  editStrategyId?: string;
  editName?: string;
  editDescription?: string;
  editInstrumentSelection?: StrategyInstrumentSelection;
  editEnabled?: boolean;
};

function createCustomBuilderInitialState(
  initialParams: CustomBuilderParams | undefined,
  initialParamsV1: StrategyParamsV1 | undefined,
  editName: string | undefined,
  editDescription: string | undefined,
  editInstrumentSelection: StrategyInstrumentSelection | undefined,
) {
  const base = initialParams ?? DEFAULT_CUSTOM_BUILDER_PARAMS;
  const params = { ...base, minCandles: roundUpMinCandles(base.minCandles) };
  const components = seedComponents(initialParams, initialParamsV1);
  const title = clampStrategyTitle(editName ?? "Custom Strategy");
  const notes = editDescription ?? "";
  const instrumentSelection = editInstrumentSelection ?? emptyInstrumentSelection();
  return {
    params,
    components,
    title,
    notes,
    instrumentSelection,
    baselineSnapshot: strategyBuilderDirtySnapshot({
      title,
      notes,
      instrumentSelection,
      components,
      params: params as unknown as Record<string, unknown>,
    }),
  };
}

export default function CustomBuilder({
  initialParams,
  initialParamsV1,
  editStrategyId,
  editName,
  editDescription,
  editInstrumentSelection,
  editEnabled,
}: CustomBuilderProps) {
  const [initial] = useState(() =>
    createCustomBuilderInitialState(
      initialParams,
      initialParamsV1,
      editName,
      editDescription,
      editInstrumentSelection,
    ),
  );
  const [params, setParams] = useState<CustomBuilderParams>(() => initial.params);
  const [components, setComponents] = useState<StrategyBuilderComponent[]>(
    () => initial.components,
  );
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
  const [enabled, setEnabled] = useState(() => Boolean(editEnabled));
  const [versionBannerAt, setVersionBannerAt] = useState<string | null>(null);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);
  const { timeOptions } = useGeneralSettings();

  const preset = STRATEGY_PRESETS.find((p) => p.id === "custom");
  const supportedAssetClasses = preset?.assetClasses ?? ALL_ASSET_CLASSES;
  const isEditMode = Boolean(editStrategyId);
  const isDirty =
    strategyBuilderDirtySnapshot({
      title,
      notes,
      instrumentSelection,
      components,
      params: params as unknown as Record<string, unknown>,
    }) !== initial.baselineSnapshot;
  const { requestClose, discardConfirmOpen, confirmDiscard, cancelDiscard } =
    useStrategyBuilderExit(isDirty);

  const handleLoadVersion = useCallback(async (versionId: string) => {
    if (!editStrategyId) return;
    const detail = await api.getStrategyVersion(editStrategyId, versionId);
    const normalized = normalizeVersionSnapshotForBuilder(detail.snapshot);
    const builderParams = v1ToCustomBuilderParams(normalized.params);
    const nextParams = {
      ...builderParams,
      minCandles: roundUpMinCandles(builderParams.minCandles),
    };
    setTitle(normalized.title);
    setNotes(normalized.notes);
    setInstrumentSelection(normalized.instrumentSelection);
    setEnabled(normalized.enabled);
    setParams(nextParams);
    setComponents(componentsFromParamsV1(normalized.params, nextParams.minCandles));
    setVersionBannerAt(detail.created_at);
  }, [editStrategyId]);

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

  useEffect(() => {
    if (initialParams) {
      setParams({ ...initialParams, minCandles: roundUpMinCandles(initialParams.minCandles) });
    }
  }, [initialParams]);

  useEffect(() => {
    if (editName) setTitle(clampStrategyTitle(editName));
  }, [editName]);

  useEffect(() => {
    if (editDescription != null) setNotes(editDescription);
  }, [editDescription]);

  useEffect(() => {
    if (editInstrumentSelection) setInstrumentSelection(editInstrumentSelection);
  }, [editInstrumentSelection]);

  useEffect(() => {
    localStorage.setItem(ACCORDION_KEY, JSON.stringify(sections));
  }, [sections]);

  const update = useCallback(<K extends keyof CustomBuilderParams>(key: K, value: CustomBuilderParams[K]) => {
    setParams((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleComponentsChange = useCallback((next: StrategyBuilderComponent[]) => {
    setComponents(next);
    const fields = applyComponentsToBuilderFields(next);
    setParams((prev) => ({
      ...prev,
      timeframe: fields.timeframe,
      minCandles: fields.minCandles,
      fastEma: fields.fastEma,
      slowEma: fields.slowEma,
      sessions: fields.sessions,
      signalType: fields.signalType,
      direction: fields.direction,
      confirmation: fields.confirmation,
    }));
  }, []);

  const computedMinCandles = useMemo(
    () =>
      computeBuilderMinCandles({
        signalType: params.signalType || undefined,
        fastEma: params.signalType === "ema_crossover" ? params.fastEma : undefined,
        slowEma: params.signalType === "ema_crossover" ? params.slowEma : undefined,
        adxFilter: params.hasAdx && params.adxFilter,
        atrFilter: params.hasAtr && params.atrFilter,
        adxPeriod: params.hasAdx ? params.adxPeriod : undefined,
        atrPeriod: params.hasAtr ? params.atrPeriod : undefined,
        slStructureLookback: params.slStructureLookback,
      }),
    [params],
  );

  const emas = getEmaComponents(components);
  const emaOverlays = useMemo(
    () =>
      getEmaComponents(components).map((ema) => ({
        id: ema.id,
        period: ema.period,
        color: ema.color,
      })),
    [components],
  );
  const signal = getSignalComponent(components);
  const crossover = emaPeriodsFromComponents(components);
  const emaInvalid =
    params.signalType === "ema_crossover" &&
    Boolean(crossover.fastEmaId) &&
    Boolean(crossover.slowEmaId) &&
    crossover.fastEma >= crossover.slowEma;
  const crossoverReady =
    params.signalType !== "ema_crossover" ||
    (Boolean(crossover.fastEmaId) &&
      Boolean(crossover.slowEmaId) &&
      crossover.fastEmaId !== crossover.slowEmaId);
  const minCandlesInvalid =
    params.minCandles < MIN_CANDLES_SLIDER_MIN ||
    params.minCandles > MIN_CANDLES_SLIDER_MAX ||
    params.minCandles < computedMinCandles ||
    computedMinCandles > MIN_CANDLES_SLIDER_MAX;
  const multiSignalUnsupported = getSignalComponents(components).length > 1;
  const canSave =
    Boolean(params.timeframe) &&
    Boolean(signal?.signalType) &&
    params.sessions.length > 0 &&
    title.trim().length > 0 &&
    !emaInvalid &&
    crossoverReady &&
    !hasDuplicateEmaPeriods(components) &&
    !minCandlesInvalid &&
    !multiSignalUnsupported;

  const riskState: RiskManagementState = useMemo(
    () => ({
      riskPerTrade: params.riskPerTrade,
      stopLossEnabled: params.stopLossEnabled,
      stopLossType: params.stopLossType,
      slAtrMultiplier: params.slAtrMultiplier,
      slFixedPips: params.slFixedPips,
      slFixedPipsJpy: params.slFixedPipsJpy,
      slStructureLookback: params.slStructureLookback,
      takeProfitEnabled: params.takeProfitEnabled,
      takeProfitType: params.takeProfitType,
      riskRewardRatio: params.riskRewardRatio,
      tpFixedPips: params.tpFixedPips,
      tpAtrMultiplier: params.tpAtrMultiplier,
      trailMode: params.trailMode,
      trailAtrMultiplier: params.trailAtrMultiplier,
      reverseCrossoverEnabled: params.reverseCrossoverEnabled,
      reverseCrossoverMinBarsAfterEntry: params.reverseCrossoverMinBarsAfterEntry,
      reverseCrossoverMinConfirmationBars: params.reverseCrossoverMinConfirmationBars,
      reverseCrossoverMinSeparationAtr: params.reverseCrossoverMinSeparationAtr,
    }),
    [params],
  );

  const saveParams = useMemo(() => {
    const base = customBuilderParamsToV1(params);
    return mergeComponentsIntoParamsV1(base, components);
  }, [params, components]);

  const signalLogic = useMemo(() => {
    const signals = getSignalComponents(components);
    if (signals.length <= 1) return undefined;
    return formatSignalLogicExpression(signals, (signal, index) => {
      const type = signal.signalType || `S${index + 1}`;
      return type === "ema_crossover"
        ? "EMA Cross"
        : type === "monthly_high"
          ? "Monthly High"
          : type === "monthly_low"
            ? "Monthly Low"
            : `S${index + 1}`;
    });
  }, [components]);

  return (
    <div className="strategy-builder">
      <div className="strategy-builder-body">
        {versionBannerAt ? (
          <div className="strategy-builder-version-banner" role="status">
            Viewing version from{" "}
            {formatAppInstant(versionBannerAt, timeOptions, "short")} — Save to keep these
            changes.
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
          supportedAssetClasses={supportedAssetClasses}
          onClose={requestClose}
          currentVersion={currentVersion}
        />

        <div className="strategy-builder-main">
          <div className="strategy-builder-chart-area">
            {emas.length > 0 ? (
              <StrategyChartShell
                params={{
                  ...params,
                  // Chart pane visibility keys off adxFilter/atrFilter; gate on has* so
                  // unused filters do not force ADX/ATR panes open.
                  adxFilter: params.hasAdx && params.adxFilter,
                  atrFilter: params.hasAtr && params.atrFilter,
                  overlays: {
                    ...params.overlays,
                    adx: params.hasAdx && params.overlays.adx,
                    atr: params.hasAtr && params.overlays.atr,
                  },
                }}
                locked
                emaOverlays={emaOverlays}
                onOverlayChange={() => undefined}
              />
            ) : (
              <div className="strategy-chart-placeholder">
                <p>
                  {params.signalType === "ema_crossover"
                    ? "Add EMA indicators to preview the chart."
                    : "Add an EMA indicator to preview the chart."}
                </p>
              </div>
            )}
          </div>

          <aside className={`strategy-builder-panel${panelOpen ? " strategy-builder-panel--open" : ""}`}>
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
              <StrategyComponentsPanel
                components={components}
                computedMinCandles={computedMinCandles}
                onChange={handleComponentsChange}
              />

              {multiSignalUnsupported ? (
                <p className="param-helper param-helper--warn">
                  Multiple signals are not saved yet — keep a single signal to save this strategy.
                </p>
              ) : null}

              <FiltersSection
                expanded={sections.filters}
                onToggle={() => setSections((s) => ({ ...s, filters: !s.filters }))}
                composable
                adx={
                  params.hasAdx
                    ? {
                        enabled: params.adxFilter,
                        period: params.adxPeriod,
                        threshold: params.adxThreshold,
                      }
                    : undefined
                }
                atr={
                  params.hasAtr
                    ? {
                        enabled: params.atrFilter,
                        period: params.atrPeriod,
                        minAtr: params.minAtr,
                        minAtrJpy: params.minAtrJpy,
                      }
                    : undefined
                }
                htfBias={{
                  enabled: params.htfBiasEnabled,
                  timeframe: params.htfBiasTimeframe,
                }}
                onAdxChange={(adx) => {
                  update("adxFilter", adx.enabled);
                  update("adxPeriod", adx.period);
                  update("adxThreshold", adx.threshold);
                }}
                onAtrChange={(atr) => {
                  update("atrFilter", atr.enabled);
                  update("atrPeriod", atr.period);
                  update("minAtr", atr.minAtr);
                  update("minAtrJpy", atr.minAtrJpy);
                }}
                onHtfBiasChange={(htf) => {
                  update("htfBiasEnabled", htf.enabled);
                  update("htfBiasTimeframe", htf.timeframe);
                }}
                onAddFilter={(type) => {
                  setParams((prev) => {
                    if (type === "adx") {
                      return {
                        ...prev,
                        hasAdx: true,
                        overlays: { ...prev.overlays, adx: true },
                      };
                    }
                    if (type === "atr") {
                      return {
                        ...prev,
                        hasAtr: true,
                        overlays: { ...prev.overlays, atr: true },
                      };
                    }
                    return prev;
                  });
                }}
                onRemoveFilter={(type) => {
                  if (type === "adx") update("hasAdx", false);
                  if (type === "atr") update("hasAtr", false);
                }}
              />

              {params.signalType === "ema_crossover" ? (
                <SignalRulesSection
                  expanded={sections.signalRules}
                  onToggle={() => setSections((s) => ({ ...s, signalRules: !s.signalRules }))}
                  direction={params.direction}
                  confirmation={params.confirmation}
                  onDirectionChange={(v) => update("direction", v)}
                  onConfirmationChange={(v) => update("confirmation", v)}
                  approachingEnabled={params.approachingEnabled}
                  approachingMaxGapAtr={params.approachingMaxGapAtr}
                  approachingMinNarrowBars={params.approachingMinNarrowBars}
                  onApproachingEnabledChange={(v) => update("approachingEnabled", v)}
                  onApproachingMaxGapAtrChange={(v) => update("approachingMaxGapAtr", v)}
                  onApproachingMinNarrowBarsChange={(v) => update("approachingMinNarrowBars", v)}
                />
              ) : null}

              <RiskManagementSection
                expanded={sections.risk}
                onToggle={() => setSections((s) => ({ ...s, risk: !s.risk }))}
                state={riskState}
                emaSignalActive={params.signalType === "ema_crossover"}
                onChange={(key, value) =>
                  setParams((prev) => ({ ...prev, [key]: value }))
                }
              />

              <ExecutionSection
                expanded={sections.execution}
                onToggle={() => setSections((s) => ({ ...s, execution: !s.execution }))}
                sessions={params.sessions}
                onSessionsChange={(sessions) => {
                  const markets = getMarketsComponent(components);
                  if (!markets) {
                    update("sessions", sessions);
                    return;
                  }
                  handleComponentsChange(
                    updateComponent(components, markets.id, { sessions }),
                  );
                }}
                minConfidence={params.minConfidence}
                maxTradesPerDay={params.maxTradesPerDay}
                overrideAllStrategies={params.overrideAllStrategies}
                dontHoldBetweenSessions={params.dontHoldBetweenSessions}
                dontHoldBetweenMarkets={params.dontHoldBetweenMarkets}
                closeBeforeMarketHours={params.closeBeforeMarketHours}
                noLateMarketTrading={params.noLateMarketTrading}
                lateMarketHours={params.lateMarketHours}
                postStopCooldownBars={params.postStopCooldownBars}
                onMinConfidenceChange={(v) => update("minConfidence", v)}
                onMaxTradesChange={(v) => update("maxTradesPerDay", v)}
                onOverrideChange={(v) => update("overrideAllStrategies", v)}
                onDontHoldBetweenSessionsChange={(v) => update("dontHoldBetweenSessions", v)}
                onDontHoldBetweenMarketsChange={(v) => update("dontHoldBetweenMarkets", v)}
                onCloseBeforeMarketHoursChange={(v) => update("closeBeforeMarketHours", v)}
                onNoLateMarketTradingChange={(v) => update("noLateMarketTrading", v)}
                onLateMarketHoursChange={(v) => update("lateMarketHours", v)}
                onPostStopCooldownBarsChange={(v) => update("postStopCooldownBars", v)}
              />
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

      {saveOverlayOpen && preset && (
        <SaveStrategyOverlay
          mode={isEditMode ? "edit" : "create"}
          strategyId={editStrategyId}
          presetId={preset.id}
          presetLabel={preset.label}
          strategyName={title}
          notes={notes}
          params={saveParams}
          instrumentSelection={instrumentSelection}
          signalLogic={signalLogic}
          initialEnabled={enabled}
          onClose={() => setSaveOverlayOpen(false)}
        />
      )}
    </div>
  );
}
