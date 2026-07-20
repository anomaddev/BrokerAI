import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../../../api/client";
import DiscardStrategyChangesDialog from "../../../../components/strategies/DiscardStrategyChangesDialog";
import SaveStrategyOverlay from "../../../../components/strategies/SaveStrategyOverlay";
import StrategyBuilderFooter from "../../../../components/strategies/StrategyBuilderFooter";
import StrategyBuilderHeader from "../../../../components/strategies/StrategyBuilderHeader";
import StrategyVersionHistoryOverlay from "../../../../components/strategies/StrategyVersionHistoryOverlay";
import StrategyComponentsPanel from "../../../../components/strategies/components/StrategyComponentsPanel";
import StrategyChartShell from "../../../../components/strategies/chart/StrategyChartShell";
import MockStatsStrip from "../../../../components/strategies/chart/MockStatsStrip";
import { useGeneralSettings } from "../../../../hooks/useGeneralSettings";
import { formatAppInstant } from "../../../../lib/formatTime";
import { normalizeVersionSnapshotForBuilder } from "../../../../lib/strategyBuilder/loadVersion";
import {
  ExecutionSection,
  FiltersSection,
  RiskManagementSection,
  type RiskManagementState,
} from "../../../../components/strategies/params/sections";
import { useStrategyBuilderExit } from "../../../../hooks/useStrategyBuilderExit";
import {
  DEFAULT_EMA_CROSSOVER_PARAMS,
  type EmaCrossoverParams,
} from "./defaults";
import { emaCrossoverParamsToV1, v1ToEmaCrossoverParams } from "./apiParams";
import { EMA_CROSSOVER_METADATA } from "./metadata";
import { STRATEGY_PRESETS } from "../../presets";
import {
  ALL_ASSET_CLASSES,
  emptyInstrumentSelection,
  type StrategyInstrumentSelection,
} from "../../../../lib/strategies/instruments";
import {
  MIN_CANDLES_SLIDER_MAX,
  MIN_CANDLES_SLIDER_MIN,
  computeBuilderMinCandles,
  roundUpMinCandles,
} from "../../../../lib/strategyParams/helpers";
import {
  clampStrategyTitle,
  formatSignalLogicExpression,
  getEmaComponents,
  getMarketsComponent,
  getSignalComponent,
  getSignalComponents,
  hasDuplicateEmaPeriods,
  seedEmaCrossoverComponents,
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
  computeAtr,
  computeSlTpDistances,
  previewPairFromSelection,
  generateMockCandles,
  mockRiskAmount,
} from "./mockData";

const ACCORDION_KEY = "brokerai-ema-crossover-accordion-v10";
const DEFAULT_SECTIONS = {
  filters: true,
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
  initialParams: EmaCrossoverParams | undefined,
  initialV1: StrategyParamsV1 | undefined,
  minCandles: number,
): StrategyBuilderComponent[] {
  if (initialV1) return componentsFromParamsV1(initialV1, minCandles);
  if (initialParams) {
    const v1 = emaCrossoverParamsToV1(initialParams);
    return componentsFromParamsV1(v1, initialParams.minCandles);
  }
  return seedEmaCrossoverComponents(minCandles);
}

type EmaCrossoverBuilderProps = {
  initialParams?: EmaCrossoverParams;
  initialParamsV1?: StrategyParamsV1;
  editStrategyId?: string;
  editName?: string;
  editDescription?: string;
  editInstrumentSelection?: StrategyInstrumentSelection;
  editEnabled?: boolean;
};

function createEmaBuilderInitialState(
  initialParams: EmaCrossoverParams | undefined,
  initialParamsV1: StrategyParamsV1 | undefined,
  editName: string | undefined,
  editDescription: string | undefined,
  editInstrumentSelection: StrategyInstrumentSelection | undefined,
) {
  const base = initialParams ?? DEFAULT_EMA_CROSSOVER_PARAMS;
  const params = { ...base, minCandles: roundUpMinCandles(base.minCandles) };
  const components = seedComponents(initialParams, initialParamsV1, params.minCandles);
  const title = clampStrategyTitle(editName ?? EMA_CROSSOVER_METADATA.label);
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

export default function EmaCrossoverBuilder({
  initialParams,
  initialParamsV1,
  editStrategyId,
  editName,
  editDescription,
  editInstrumentSelection,
  editEnabled,
}: EmaCrossoverBuilderProps) {
  const [initial] = useState(() =>
    createEmaBuilderInitialState(
      initialParams,
      initialParamsV1,
      editName,
      editDescription,
      editInstrumentSelection,
    ),
  );
  const [params, setParams] = useState<EmaCrossoverParams>(() => initial.params);
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
  const [statsExpanded, setStatsExpanded] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [saveOverlayOpen, setSaveOverlayOpen] = useState(false);
  const [historyOverlayOpen, setHistoryOverlayOpen] = useState(false);
  const [enabled, setEnabled] = useState(() => Boolean(editEnabled));
  const [versionBannerAt, setVersionBannerAt] = useState<string | null>(null);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);
  const { timeOptions } = useGeneralSettings();

  const preset = STRATEGY_PRESETS.find((p) => p.id === "ema_crossover");
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
    const builderParams = v1ToEmaCrossoverParams(normalized.params);
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

  const update = useCallback(<K extends keyof EmaCrossoverParams>(key: K, value: EmaCrossoverParams[K]) => {
    setParams((prev) => ({ ...prev, [key]: value }));
  }, []);

  const updateOverlay = useCallback(
    (key: keyof EmaCrossoverParams["overlays"], value: boolean) => {
      setParams((prev) => ({
        ...prev,
        overlays: { ...prev.overlays, [key]: value },
      }));
    },
    [],
  );

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
      direction: fields.direction,
      confirmation: fields.confirmation,
    }));
  }, []);

  const toggleSection = (key: SectionKey) => {
    setSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const computedMinCandles = useMemo(
    () =>
      computeBuilderMinCandles({
        fastEma: params.fastEma,
        slowEma: params.slowEma,
        adxFilter: params.adxFilter,
        atrFilter: params.atrFilter,
        adxPeriod: params.adxPeriod,
        atrPeriod: params.atrPeriod,
        slStructureLookback: params.slStructureLookback,
      }),
    [params],
  );

  const emaOverlays = useMemo(
    () =>
      getEmaComponents(components).map((ema) => ({
        id: ema.id,
        period: ema.period,
        color: ema.color,
      })),
    [components],
  );
  const crossover = emaPeriodsFromComponents(components);
  const signal = getSignalComponent(components);
  const emaInvalid =
    Boolean(crossover.fastEmaId) &&
    Boolean(crossover.slowEmaId) &&
    crossover.fastEma >= crossover.slowEma;
  const crossoverReady =
    signal?.signalType === "ema_crossover" &&
    Boolean(crossover.fastEmaId) &&
    Boolean(crossover.slowEmaId) &&
    crossover.fastEmaId !== crossover.slowEmaId;
  const minCandlesInvalid =
    params.minCandles < MIN_CANDLES_SLIDER_MIN ||
    params.minCandles > MIN_CANDLES_SLIDER_MAX ||
    params.minCandles < computedMinCandles ||
    computedMinCandles > MIN_CANDLES_SLIDER_MAX;
  const multiSignalUnsupported = getSignalComponents(components).length > 1;
  const canSave =
    Boolean(params.timeframe) &&
    params.sessions.length > 0 &&
    title.trim().length > 0 &&
    crossoverReady &&
    !emaInvalid &&
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
    }),
    [params],
  );

  const onRiskChange = useCallback(
    <K extends keyof RiskManagementState>(key: K, value: RiskManagementState[K]) => {
      setParams((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const mockRisk = useMemo(() => {
    const candles = generateMockCandles(120);
    const atr = computeAtr(candles, params.atrPeriod);
    const entry = candles[candles.length - 1].close;
    const previewPair = previewPairFromSelection(params.selectedInstruments);
    const { slDistance } = computeSlTpDistances(params, candles, atr, entry, previewPair);
    return mockRiskAmount(params.riskPerTrade, slDistance, entry);
  }, [params]);

  const lastSignalLabel = useMemo(() => {
    if (params.direction === "short") return "Bearish cross · 2h ago";
    return "Bullish cross · 2h ago";
  }, [params.direction]);

  const saveParams = useMemo(() => {
    const base = emaCrossoverParamsToV1(params);
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
            <StrategyChartShell
              params={params}
              locked
              emaOverlays={emaOverlays}
              onOverlayChange={updateOverlay}
            />
            <MockStatsStrip
              expanded={statsExpanded}
              onToggle={() => setStatsExpanded((v) => !v)}
              lastSignal={lastSignalLabel}
              adx={28.4}
              atr={0.0012}
              confidence={72}
              mockRisk={mockRisk}
            />
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
                signalLocked
              />

              {emaInvalid ? (
                <p className="param-helper param-helper--warn">
                  Fast and slow EMA periods must differ.
                </p>
              ) : null}
              {multiSignalUnsupported ? (
                <p className="param-helper param-helper--warn">
                  Multiple signals are not saved yet — keep a single signal to save this strategy.
                </p>
              ) : null}

              <FiltersSection
                expanded={sections.filters}
                onToggle={() => toggleSection("filters")}
                adx={{
                  enabled: params.adxFilter,
                  period: params.adxPeriod,
                  threshold: params.adxThreshold,
                }}
                atr={{
                  enabled: params.atrFilter,
                  period: params.atrPeriod,
                  minAtr: params.minAtr,
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
                }}
              />

              <RiskManagementSection
                expanded={sections.risk}
                onToggle={() => toggleSection("risk")}
                state={riskState}
                emaSignalActive
                onChange={onRiskChange}
              />

              <ExecutionSection
                expanded={sections.execution}
                onToggle={() => toggleSection("execution")}
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
                onMinConfidenceChange={(v) => update("minConfidence", v)}
                onMaxTradesChange={(v) => update("maxTradesPerDay", v)}
                onOverrideChange={(v) => update("overrideAllStrategies", v)}
                onDontHoldBetweenSessionsChange={(v) => update("dontHoldBetweenSessions", v)}
                onDontHoldBetweenMarketsChange={(v) => update("dontHoldBetweenMarkets", v)}
                onCloseBeforeMarketHoursChange={(v) => update("closeBeforeMarketHours", v)}
                onNoLateMarketTradingChange={(v) => update("noLateMarketTrading", v)}
                onLateMarketHoursChange={(v) => update("lateMarketHours", v)}
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
