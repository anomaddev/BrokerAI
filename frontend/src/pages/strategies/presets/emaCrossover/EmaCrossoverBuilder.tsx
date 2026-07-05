import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { ROUTES } from "../../../../lib/routes";
import SaveStrategyOverlay from "../../../../components/strategies/SaveStrategyOverlay";
import StrategyChartShell from "../../../../components/strategies/chart/StrategyChartShell";
import MockStatsStrip from "../../../../components/strategies/chart/MockStatsStrip";
import {
  ExecutionSection,
  FiltersSection,
  RiskManagementSection,
  SignalRulesSection,
  SignalSection,
  TimeframeSection,
  type RiskManagementState,
} from "../../../../components/strategies/params/sections";
import {
  DEFAULT_EMA_CROSSOVER_PARAMS,
  SESSION_OPTIONS,
  type EmaCrossoverParams,
} from "./defaults";
import { emaCrossoverParamsToV1 } from "./apiParams";
import { EMA_CROSSOVER_METADATA } from "./metadata";
import { STRATEGY_PRESETS } from "../../presets";
import { ALL_ASSET_CLASSES } from "../../strategyAssignment";
import { computeBuilderMinCandles } from "../../../../lib/strategyParams/helpers";
import {
  computeAtr,
  computeSlTpDistances,
  generateMockCandles,
  mockRiskAmount,
} from "./mockData";

const ACCORDION_KEY = "brokerai-ema-crossover-accordion-v8";
const DEFAULT_SECTIONS = {
  timeframe: true,
  signal: true,
  filters: true,
  signals: true,
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

function ParametersPanelHeader({ variant }: { variant: "paired" | "in-panel" }) {
  return (
    <div className={`strategy-builder-panel-header strategy-builder-panel-header--${variant}`}>
      <h2 className="strategy-builder-panel-title">Parameters</h2>
    </div>
  );
}

type EmaCrossoverBuilderProps = {
  initialParams?: EmaCrossoverParams;
  editStrategyId?: string;
  editName?: string;
  editDescription?: string;
  editInstrumentSelection?: import("../../../../lib/strategies/instruments").StrategyInstrumentSelection;
  editEnabled?: boolean;
};

export default function EmaCrossoverBuilder({
  initialParams,
  editStrategyId,
  editName,
  editDescription,
  editInstrumentSelection,
  editEnabled,
}: EmaCrossoverBuilderProps) {
  const [params, setParams] = useState<EmaCrossoverParams>(initialParams ?? DEFAULT_EMA_CROSSOVER_PARAMS);
  const [sections, setSections] = useState(loadSections);
  const [statsExpanded, setStatsExpanded] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [saveOverlayOpen, setSaveOverlayOpen] = useState(false);

  const preset = STRATEGY_PRESETS.find((p) => p.id === "ema_crossover");
  const isEditMode = Boolean(editStrategyId);

  useEffect(() => {
    if (initialParams) {
      setParams(initialParams);
    }
  }, [initialParams]);

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

  const emaInvalid = params.fastEma >= params.slowEma;
  const minCandlesInvalid = params.minCandles < computedMinCandles || params.minCandles > 2000 || computedMinCandles > 2000;
  const canSave = Boolean(params.timeframe) && !emaInvalid && !minCandlesInvalid;

  const riskState: RiskManagementState = useMemo(
    () => ({
      riskPerTrade: params.riskPerTrade,
      stopLossType: params.stopLossType,
      slAtrMultiplier: params.slAtrMultiplier,
      slFixedPips: params.slFixedPips,
      slStructureLookback: params.slStructureLookback,
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
    const { slDistance } = computeSlTpDistances(params, candles, atr, entry);
    return mockRiskAmount(params.riskPerTrade, slDistance, entry);
  }, [params]);

  const lastSignalLabel = useMemo(() => {
    if (params.direction === "short") return "Bearish cross · 2h ago";
    return "Bullish cross · 2h ago";
  }, [params.direction]);

  return (
    <div className="strategy-builder">
      <div className="strategy-builder-body">
        <div className="strategy-builder-top-row">
          <div className="strategy-chart-area-bar">
            <div className="strategy-chart-area-bar-main">
              <Link to={ROUTES.research.strategies} className="strategy-builder-back-btn">
                <ArrowLeft size={16} aria-hidden="true" />
                <span>Strategies</span>
              </Link>
              <span className="strategy-chart-area-divider" aria-hidden="true" />
              <div className="strategy-chart-area-bar-title">
                <h1 className="strategy-builder-title">{EMA_CROSSOVER_METADATA.label}</h1>
                <span className="strategy-meta-chip strategy-meta-chip--accent">Template</span>
              </div>
            </div>
          </div>
          <ParametersPanelHeader variant="paired" />
        </div>

        <div className="strategy-builder-main">
          <div className="strategy-builder-chart-area">
            <StrategyChartShell params={params} locked onOverlayChange={updateOverlay} />
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
            <ParametersPanelHeader variant="in-panel" />
            <div className="strategy-builder-panel-scroll">
              <TimeframeSection
                expanded={sections.timeframe}
                onToggle={() => toggleSection("timeframe")}
                timeframe={params.timeframe}
                minCandles={params.minCandles}
                computedMinCandles={computedMinCandles}
                onTimeframeChange={(v) => update("timeframe", v)}
                onMinCandlesChange={(v) => update("minCandles", v)}
              />

              <SignalSection
                expanded={sections.signal}
                onToggle={() => toggleSection("signal")}
                signalType="ema_crossover"
                locked
                fastEma={params.fastEma}
                slowEma={params.slowEma}
                onFastEmaChange={(v) => update("fastEma", v)}
                onSlowEmaChange={(v) => update("slowEma", v)}
              />

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

              <SignalRulesSection
                expanded={sections.signals}
                onToggle={() => toggleSection("signals")}
                direction={params.direction}
                confirmation={params.confirmation}
                onDirectionChange={(v) => update("direction", v)}
                onConfirmationChange={(v) => update("confirmation", v)}
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
                minConfidence={params.minConfidence}
                maxTradesPerDay={params.maxTradesPerDay}
                overrideAllStrategies={params.overrideAllStrategies}
                priority={params.priority}
                onMinConfidenceChange={(v) => update("minConfidence", v)}
                onMaxTradesChange={(v) => update("maxTradesPerDay", v)}
                onOverrideChange={(v) => update("overrideAllStrategies", v)}
                onPriorityChange={(v) => update("priority", v)}
              />
            </div>
            <div className="strategy-builder-panel-footer">
              <button
                type="button"
                className="btn"
                onClick={() => setSaveOverlayOpen(true)}
                disabled={!canSave}
                title={canSave ? undefined : "Complete required parameters to save"}
              >
                {isEditMode ? "Save changes" : "Create Strategy"}
              </button>
            </div>
          </aside>
        </div>
      </div>

      <button
        type="button"
        className="strategy-builder-panel-fab"
        onClick={() => setPanelOpen((v) => !v)}
        aria-expanded={panelOpen}
      >
        Parameters
      </button>

      {saveOverlayOpen && preset && (
        <SaveStrategyOverlay
          mode={isEditMode ? "edit" : "create"}
          strategyId={editStrategyId}
          presetId={preset.id}
          templateName={editName ?? preset.label}
          templateDescription={editDescription ?? preset.description}
          supportedAssetClasses={ALL_ASSET_CLASSES}
          templatePills={preset.enabledPills}
          params={emaCrossoverParamsToV1(params)}
          sessionDefaults={[...DEFAULT_EMA_CROSSOVER_PARAMS.sessions]}
          sessionOptions={SESSION_OPTIONS}
          initialInstrumentSelection={editInstrumentSelection}
          initialEnabled={editEnabled}
          onClose={() => setSaveOverlayOpen(false)}
        />
      )}
    </div>
  );
}
