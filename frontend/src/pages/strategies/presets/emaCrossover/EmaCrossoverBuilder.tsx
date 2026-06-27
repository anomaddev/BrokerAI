import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import CreateStrategyFromTemplateOverlay from "../../../../components/strategies/CreateStrategyFromTemplateOverlay";
import StrategyChartShell from "../../../../components/strategies/chart/StrategyChartShell";
import MockStatsStrip from "../../../../components/strategies/chart/MockStatsStrip";
import ParameterCard from "../../../../components/strategies/params/ParameterCard";
import LiveSlider from "../../../../components/strategies/params/LiveSlider";
import NumberStepper from "../../../../components/strategies/params/NumberStepper";
import SegmentedControl from "../../../../components/strategies/params/SegmentedControl";
import TimeframeSelect from "../../../../components/strategies/params/TimeframeSelect";
import ParamToggleRow from "../../../../components/strategies/params/ParamToggleRow";
import {
  DEFAULT_EMA_CROSSOVER_PARAMS,
  SESSION_OPTIONS,
  TIMEFRAME_OPTIONS,
  type EmaCrossoverParams,
} from "./defaults";
import { emaCrossoverBuilderParamsToApi } from "./apiParams";
import { EMA_CROSSOVER_METADATA } from "./metadata";
import { STRATEGY_PRESETS } from "../../presets";
import { ALL_ASSET_CLASSES } from "../../strategyAssignment";
import {
  computeAtr,
  computeSlTpDistances,
  generateMockCandles,
  mockRiskAmount,
} from "./mockData";

const ACCORDION_KEY = "brokerai-ema-crossover-accordion-v8";
const DEFAULT_SECTIONS = {
  timeframe: true,
  core: true,
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

export default function EmaCrossoverBuilder() {
  const [params, setParams] = useState<EmaCrossoverParams>(DEFAULT_EMA_CROSSOVER_PARAMS);
  const [sections, setSections] = useState(loadSections);
  const [statsExpanded, setStatsExpanded] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [createOverlayOpen, setCreateOverlayOpen] = useState(false);

  const preset = STRATEGY_PRESETS.find((p) => p.id === "ema_crossover");

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

  const emaInvalid = params.fastEma >= params.slowEma;
  const canCreate = Boolean(params.timeframe);
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
              <Link to="/trading/strategies" className="strategy-builder-back-btn">
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
            <ParameterCard
              title="Timeframe"
              required
              expanded={sections.timeframe}
              onToggle={() => toggleSection("timeframe")}
              badge={!params.timeframe ? "!" : undefined}
            >
              <TimeframeSelect
                value={params.timeframe}
                options={TIMEFRAME_OPTIONS}
                onChange={(v) => update("timeframe", v)}
              />
            </ParameterCard>

            <ParameterCard
              title="Core EMA Settings"
              expanded={sections.core}
              onToggle={() => toggleSection("core")}
              badge={emaInvalid ? "!" : undefined}
            >
              <LiveSlider
                id="fast-ema"
                label="Fast EMA period"
                value={params.fastEma}
                min={3}
                max={50}
                showStepper
                onChange={(v) => update("fastEma", v)}
              />
              <LiveSlider
                id="slow-ema"
                label="Slow EMA period"
                value={params.slowEma}
                min={10}
                max={200}
                showStepper
                invalid={emaInvalid}
                onChange={(v) => update("slowEma", v)}
              />
              {emaInvalid && (
                <p className="param-helper param-helper--warn">Fast must be less than slow EMA.</p>
              )}
            </ParameterCard>

            <ParameterCard
              title="Trend & Volatility Filters"
              expanded={sections.filters}
              onToggle={() => toggleSection("filters")}
            >
              <ParamToggleRow
                label="ADX filter"
                checked={params.adxFilter}
                onChange={(v) => update("adxFilter", v)}
              >
                <NumberStepper
                  id="adx-period"
                  label="ADX period"
                  value={params.adxPeriod}
                  min={7}
                  max={28}
                  onChange={(v) => update("adxPeriod", v)}
                />
                <LiveSlider
                  id="adx-threshold"
                  label="ADX threshold"
                  value={params.adxThreshold}
                  min={15}
                  max={40}
                  onChange={(v) => update("adxThreshold", v)}
                />
              </ParamToggleRow>
              <ParamToggleRow
                label="ATR filter"
                checked={params.atrFilter}
                onChange={(v) => update("atrFilter", v)}
              >
                <NumberStepper
                  id="atr-period"
                  label="ATR period"
                  value={params.atrPeriod}
                  min={7}
                  max={28}
                  onChange={(v) => update("atrPeriod", v)}
                />
                <LiveSlider
                  id="min-atr"
                  label="Min ATR value"
                  value={params.minAtr}
                  min={0.0001}
                  max={0.005}
                  step={0.0001}
                  formatValue={(v) => v.toFixed(4)}
                  onChange={(v) => update("minAtr", v)}
                />
              </ParamToggleRow>
            </ParameterCard>

            <ParameterCard
              title="Signal Rules"
              expanded={sections.signals}
              onToggle={() => toggleSection("signals")}
            >
              <SegmentedControl
                label="Direction"
                value={params.direction}
                options={[
                  { value: "long", label: "Long" },
                  { value: "short", label: "Short" },
                  { value: "both", label: "Both" },
                ]}
                onChange={(v) => update("direction", v)}
              />
              <SegmentedControl
                label="Confirmation"
                value={params.confirmation}
                options={[
                  { value: "close", label: "Close" },
                  { value: "pullback", label: "Pullback" },
                  { value: "aggressive", label: "Aggressive" },
                ]}
                onChange={(v) => update("confirmation", v)}
              />
            </ParameterCard>

            <ParameterCard
              title="Risk Management"
              expanded={sections.risk}
              onToggle={() => toggleSection("risk")}
            >
              <div className="param-control">
                <label htmlFor="sl-type" className="param-control-label">
                  Stop Loss type
                </label>
                <select
                  id="sl-type"
                  className="research-select"
                  value={params.stopLossType}
                  onChange={(e) =>
                    update("stopLossType", e.target.value as EmaCrossoverParams["stopLossType"])
                  }
                >
                  <option value="fixed_pips">Fixed pips</option>
                  <option value="atr_based">ATR-based</option>
                  <option value="structure">Structure</option>
                </select>
              </div>

              {params.stopLossType === "fixed_pips" && (
                <LiveSlider
                  id="sl-pips"
                  label="SL distance (pips)"
                  value={params.slFixedPips}
                  min={5}
                  max={100}
                  showStepper
                  onChange={(v) => update("slFixedPips", v)}
                />
              )}

              {params.stopLossType === "atr_based" && (
                <LiveSlider
                  id="sl-atr"
                  label="SL ATR multiplier"
                  value={params.slAtrMultiplier}
                  min={0.5}
                  max={4}
                  step={0.1}
                  formatValue={(v) => v.toFixed(1)}
                  onChange={(v) => update("slAtrMultiplier", v)}
                />
              )}

              {params.stopLossType === "structure" && (
                <>
                  <NumberStepper
                    id="sl-structure-lookback"
                    label="Structure lookback (bars)"
                    value={params.slStructureLookback}
                    min={3}
                    max={50}
                    onChange={(v) => update("slStructureLookback", v)}
                  />
                  <p className="param-helper">
                    SL placed below the swing low over the lookback window.
                  </p>
                </>
              )}

              <div className="param-control">
                <label htmlFor="tp-type" className="param-control-label">
                  Take Profit type
                </label>
                <select
                  id="tp-type"
                  className="research-select"
                  value={params.takeProfitType}
                  onChange={(e) =>
                    update("takeProfitType", e.target.value as EmaCrossoverParams["takeProfitType"])
                  }
                >
                  <option value="fixed_pips">Fixed pips</option>
                  <option value="rr_ratio">R:R ratio</option>
                  <option value="atr_based">ATR-based</option>
                </select>
              </div>

              {params.takeProfitType === "fixed_pips" && (
                <LiveSlider
                  id="tp-pips"
                  label="TP distance (pips)"
                  value={params.tpFixedPips}
                  min={5}
                  max={200}
                  showStepper
                  onChange={(v) => update("tpFixedPips", v)}
                />
              )}

              {params.takeProfitType === "rr_ratio" && (
                <>
                  <LiveSlider
                    id="rr-ratio"
                    label="Risk/Reward ratio"
                    value={params.riskRewardRatio}
                    min={1}
                    max={5}
                    step={0.1}
                    formatValue={(v) => `${v.toFixed(1)}:1`}
                    onChange={(v) => update("riskRewardRatio", v)}
                  />
                  <p className="param-helper">
                    TP distance is {params.riskRewardRatio.toFixed(1)}× the stop loss distance.
                  </p>
                </>
              )}

              {params.takeProfitType === "atr_based" && (
                <LiveSlider
                  id="tp-atr"
                  label="TP ATR multiplier"
                  value={params.tpAtrMultiplier}
                  min={0.5}
                  max={6}
                  step={0.1}
                  formatValue={(v) => v.toFixed(1)}
                  onChange={(v) => update("tpAtrMultiplier", v)}
                />
              )}

              <ParamToggleRow
                label="Trailing stop"
                checked={params.trailingStop}
                onChange={(v) => update("trailingStop", v)}
              >
                <LiveSlider
                  id="trail-atr"
                  label="Trail ATR multiplier"
                  value={params.trailAtrMultiplier}
                  min={0.5}
                  max={3}
                  step={0.1}
                  formatValue={(v) => v.toFixed(1)}
                  onChange={(v) => update("trailAtrMultiplier", v)}
                />
              </ParamToggleRow>
              <LiveSlider
                id="risk-pct"
                label="Risk per trade %"
                value={params.riskPerTrade}
                min={0.25}
                max={5}
                step={0.25}
                unit="%"
                onChange={(v) => update("riskPerTrade", v)}
              />
            </ParameterCard>

            <ParameterCard
              title="Execution"
              expanded={sections.execution}
              onToggle={() => toggleSection("execution")}
            >
              <LiveSlider
                id="min-confidence"
                label="Min confidence threshold"
                value={params.minConfidence}
                min={0}
                max={100}
                unit="%"
                onChange={(v) => update("minConfidence", v)}
              />
              <NumberStepper
                id="max-trades"
                label="Max trades per day"
                value={params.maxTradesPerDay}
                min={1}
                max={20}
                onChange={(v) => update("maxTradesPerDay", v)}
              />
              <ParamToggleRow
                label="Override all other strategies"
                checked={params.overrideAllStrategies}
                onChange={(v) => update("overrideAllStrategies", v)}
              />
            </ParameterCard>
          </div>
          <div className="strategy-builder-panel-footer">
            <button
              type="button"
              className="btn"
              onClick={() => setCreateOverlayOpen(true)}
              disabled={!canCreate}
              title={canCreate ? undefined : "Select a timeframe to create this strategy"}
            >
              Create Strategy
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

      {createOverlayOpen && preset && (
        <CreateStrategyFromTemplateOverlay
          presetId={preset.id}
          templateName={preset.label}
          templateDescription={preset.description}
          supportedAssetClasses={ALL_ASSET_CLASSES}
          templatePills={preset.enabledPills}
          params={emaCrossoverBuilderParamsToApi(params)}
          sessionDefaults={[...DEFAULT_EMA_CROSSOVER_PARAMS.sessions]}
          sessionOptions={SESSION_OPTIONS}
          onClose={() => setCreateOverlayOpen(false)}
        />
      )}
    </div>
  );
}
