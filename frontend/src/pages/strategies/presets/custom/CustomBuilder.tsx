import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import SaveStrategyOverlay from "../../../../components/strategies/SaveStrategyOverlay";
import StrategyChartShell from "../../../../components/strategies/chart/StrategyChartShell";
import {
  ExecutionSection,
  FiltersSection,
  RiskManagementSection,
  SignalRulesSection,
  SignalSection,
  TimeframeSection,
  type RiskManagementState,
} from "../../../../components/strategies/params/sections";
import { computeBuilderMinCandles } from "../../../../lib/strategyParams/helpers";
import { STRATEGY_PRESETS } from "../../presets";
import { ALL_ASSET_CLASSES } from "../../strategyAssignment";
import {
  DEFAULT_CUSTOM_BUILDER_PARAMS,
  SESSION_OPTIONS,
  customBuilderParamsToV1,
  type CustomBuilderParams,
} from "./defaults";

const ACCORDION_KEY = "brokerai-custom-builder-accordion-v1";
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

type CustomBuilderProps = {
  initialParams?: CustomBuilderParams;
  editStrategyId?: string;
  editName?: string;
  editDescription?: string;
  editInstrumentSelection?: import("../../../../lib/strategies/instruments").StrategyInstrumentSelection;
  editEnabled?: boolean;
};

export default function CustomBuilder({
  initialParams,
  editStrategyId,
  editName,
  editDescription,
  editInstrumentSelection,
  editEnabled,
}: CustomBuilderProps) {
  const [params, setParams] = useState<CustomBuilderParams>(initialParams ?? DEFAULT_CUSTOM_BUILDER_PARAMS);
  const [sections, setSections] = useState(loadSections);
  const [panelOpen, setPanelOpen] = useState(false);
  const [saveOverlayOpen, setSaveOverlayOpen] = useState(false);

  const preset = STRATEGY_PRESETS.find((p) => p.id === "custom");
  const isEditMode = Boolean(editStrategyId);

  useEffect(() => {
    if (initialParams) setParams(initialParams);
  }, [initialParams]);

  useEffect(() => {
    localStorage.setItem(ACCORDION_KEY, JSON.stringify(sections));
  }, [sections]);

  const update = useCallback(<K extends keyof CustomBuilderParams>(key: K, value: CustomBuilderParams[K]) => {
    setParams((prev) => ({ ...prev, [key]: value }));
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

  const emaInvalid = params.signalType === "ema_crossover" && params.fastEma >= params.slowEma;
  const minCandlesInvalid =
    params.minCandles < computedMinCandles || params.minCandles > 2000 || computedMinCandles > 2000;
  const canSave = Boolean(params.timeframe) && Boolean(params.signalType) && !emaInvalid && !minCandlesInvalid;

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

  return (
    <div className="strategy-builder">
      <div className="strategy-builder-body">
        <div className="strategy-builder-top-row">
          <div className="strategy-chart-area-bar">
            <div className="strategy-chart-area-bar-main">
              <Link to="/trading/strategies" className="strategy-builder-back-btn">
                <ArrowLeft size={16} aria-hidden="true" />
                <span>Strategies</span>
              </Link>
              <span className="strategy-chart-area-divider" aria-hidden="true" />
              <div className="strategy-chart-area-bar-title">
                <h1 className="strategy-builder-title">Custom Strategy</h1>
                <span className="strategy-meta-chip strategy-meta-chip--accent">Custom</span>
              </div>
            </div>
          </div>
        </div>

        <div className="strategy-builder-main">
          <div className="strategy-builder-chart-area">
            {params.signalType === "ema_crossover" ? (
              <StrategyChartShell params={params} locked onOverlayChange={() => undefined} />
            ) : (
              <div className="strategy-chart-placeholder">
                <p>
                  {params.signalType
                    ? "Chart preview is available for EMA Crossover signals."
                    : "Select a signal to preview the chart."}
                </p>
              </div>
            )}
          </div>

          <aside className={`strategy-builder-panel${panelOpen ? " strategy-builder-panel--open" : ""}`}>
            <div className="strategy-builder-panel-handle" aria-hidden="true" />
            <div className="strategy-builder-panel-scroll">
              <TimeframeSection
                expanded={sections.timeframe}
                onToggle={() => setSections((s) => ({ ...s, timeframe: !s.timeframe }))}
                timeframe={params.timeframe}
                minCandles={params.minCandles}
                computedMinCandles={computedMinCandles}
                onTimeframeChange={(v) => update("timeframe", v)}
                onMinCandlesChange={(v) => update("minCandles", v)}
              />

              <SignalSection
                expanded={sections.signal}
                onToggle={() => setSections((s) => ({ ...s, signal: !s.signal }))}
                signalType={params.signalType}
                onSignalTypeChange={(value) => update("signalType", value)}
                fastEma={params.fastEma}
                slowEma={params.slowEma}
                onFastEmaChange={(v) => update("fastEma", v)}
                onSlowEmaChange={(v) => update("slowEma", v)}
              />

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
                      }
                    : undefined
                }
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
                onAddFilter={(type) => {
                  if (type === "adx") update("hasAdx", true);
                  if (type === "atr") update("hasAtr", true);
                }}
                onRemoveFilter={(type) => {
                  if (type === "adx") update("hasAdx", false);
                  if (type === "atr") update("hasAtr", false);
                }}
              />

              <SignalRulesSection
                expanded={sections.signals}
                onToggle={() => setSections((s) => ({ ...s, signals: !s.signals }))}
                direction={params.direction}
                confirmation={params.confirmation}
                onDirectionChange={(v) => update("direction", v)}
                onConfirmationChange={(v) => update("confirmation", v)}
              />

              <RiskManagementSection
                expanded={sections.risk}
                onToggle={() => setSections((s) => ({ ...s, risk: !s.risk }))}
                state={riskState}
                emaSignalActive={params.signalType === "ema_crossover"}
                onChange={(key, value) => update(key, value)}
              />

              <ExecutionSection
                expanded={sections.execution}
                onToggle={() => setSections((s) => ({ ...s, execution: !s.execution }))}
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
              >
                {isEditMode ? "Save changes" : "Create Strategy"}
              </button>
            </div>
          </aside>
        </div>
      </div>

      {saveOverlayOpen && preset && (
        <SaveStrategyOverlay
          mode={isEditMode ? "edit" : "create"}
          strategyId={editStrategyId}
          presetId={preset.id}
          templateName={editName ?? preset.label}
          templateDescription={editDescription ?? preset.description}
          supportedAssetClasses={ALL_ASSET_CLASSES}
          templatePills={preset.enabledPills}
          params={customBuilderParamsToV1(params)}
          sessionDefaults={[...DEFAULT_CUSTOM_BUILDER_PARAMS.sessions]}
          sessionOptions={SESSION_OPTIONS}
          initialInstrumentSelection={editInstrumentSelection}
          initialEnabled={editEnabled}
          onClose={() => setSaveOverlayOpen(false)}
        />
      )}
    </div>
  );
}
