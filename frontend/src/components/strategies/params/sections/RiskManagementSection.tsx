import ParameterCard from "../ParameterCard";
import LiveSlider from "../LiveSlider";
import NumberStepper from "../NumberStepper";
import type { StopLossMode, TakeProfitMode, TrailMode } from "../../../../lib/strategyParams";

export type RiskManagementState = {
  riskPerTrade: number;
  stopLossType: StopLossMode;
  slAtrMultiplier: number;
  slFixedPips: number;
  slStructureLookback: number;
  takeProfitType: TakeProfitMode;
  riskRewardRatio: number;
  tpFixedPips: number;
  tpAtrMultiplier: number;
  trailMode: TrailMode;
  trailAtrMultiplier: number;
};

type RiskManagementSectionProps = {
  expanded: boolean;
  onToggle: () => void;
  state: RiskManagementState;
  emaSignalActive: boolean;
  onChange: <K extends keyof RiskManagementState>(key: K, value: RiskManagementState[K]) => void;
};

export default function RiskManagementSection({
  expanded,
  onToggle,
  state,
  emaSignalActive,
  onChange,
}: RiskManagementSectionProps) {
  const tpOptions: { value: TakeProfitMode; label: string }[] = [
    { value: "fixed_pips", label: "Fixed pips" },
    { value: "rr_ratio", label: "R:R ratio" },
    { value: "atr_based", label: "ATR-based" },
  ];
  if (emaSignalActive) {
    tpOptions.push({ value: "reverse_crossover", label: "Reverse crossover" });
  }
  tpOptions.push({ value: "trailing_stop", label: "Trailing stop" });

  return (
    <ParameterCard title="Risk Management" required expanded={expanded} onToggle={onToggle}>
      <LiveSlider
        id="risk-pct"
        label="Risk per trade %"
        value={state.riskPerTrade}
        min={0.25}
        max={5}
        step={0.25}
        unit="%"
        onChange={(v) => onChange("riskPerTrade", v)}
      />

      <div className="param-control">
        <label htmlFor="sl-type" className="param-control-label">
          Stop Loss type
        </label>
        <select
          id="sl-type"
          className="research-select"
          value={state.stopLossType}
          onChange={(e) => onChange("stopLossType", e.target.value as StopLossMode)}
        >
          <option value="fixed_pips">Fixed pips</option>
          <option value="atr_based">ATR-based</option>
          <option value="structure">Structure</option>
        </select>
      </div>

      {state.stopLossType === "fixed_pips" && (
        <LiveSlider
          id="sl-pips"
          label="SL distance (pips)"
          value={state.slFixedPips}
          min={5}
          max={100}
          onChange={(v) => onChange("slFixedPips", v)}
        />
      )}

      {state.stopLossType === "atr_based" && (
        <LiveSlider
          id="sl-atr"
          label="SL ATR multiplier"
          value={state.slAtrMultiplier}
          min={0.5}
          max={4}
          step={0.1}
          formatValue={(v) => v.toFixed(1)}
          onChange={(v) => onChange("slAtrMultiplier", v)}
        />
      )}

      {state.stopLossType === "structure" && (
        <>
          <NumberStepper
            id="sl-structure-lookback"
            label="Structure lookback (bars)"
            value={state.slStructureLookback}
            min={3}
            max={50}
            onChange={(v) => onChange("slStructureLookback", v)}
          />
          <p className="param-helper">SL placed below the swing low over the lookback window.</p>
        </>
      )}

      <div className="param-control">
        <label htmlFor="tp-type" className="param-control-label">
          Take Profit type
        </label>
        <select
          id="tp-type"
          className="research-select"
          value={state.takeProfitType}
          onChange={(e) => onChange("takeProfitType", e.target.value as TakeProfitMode)}
        >
          {tpOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {state.takeProfitType === "fixed_pips" && (
        <LiveSlider
          id="tp-pips"
          label="TP distance (pips)"
          value={state.tpFixedPips}
          min={5}
          max={200}
          onChange={(v) => onChange("tpFixedPips", v)}
        />
      )}

      {state.takeProfitType === "rr_ratio" && (
        <>
          <LiveSlider
            id="rr-ratio"
            label="Risk/Reward ratio"
            value={state.riskRewardRatio}
            min={1}
            max={5}
            step={0.1}
            suffix=":1"
            formatValue={(v) => v.toFixed(1)}
            onChange={(v) => onChange("riskRewardRatio", v)}
          />
          <p className="param-helper">
            TP distance is {state.riskRewardRatio.toFixed(1)}× the stop loss distance.
          </p>
        </>
      )}

      {state.takeProfitType === "atr_based" && (
        <LiveSlider
          id="tp-atr"
          label="TP ATR multiplier"
          value={state.tpAtrMultiplier}
          min={0.5}
          max={6}
          step={0.1}
          formatValue={(v) => v.toFixed(1)}
          onChange={(v) => onChange("tpAtrMultiplier", v)}
        />
      )}

      {state.takeProfitType === "reverse_crossover" && (
        <p className="param-helper">Exit when the EMA crossover reverses direction.</p>
      )}

      {state.takeProfitType === "trailing_stop" && (
        <>
          <div className="param-control">
            <label htmlFor="trail-mode" className="param-control-label">
              Trailing stop type
            </label>
            <select
              id="trail-mode"
              className="research-select"
              value={state.trailMode}
              onChange={(e) => onChange("trailMode", e.target.value as TrailMode)}
            >
              {emaSignalActive && <option value="ema_slow">Trail EMA Slow</option>}
              <option value="atr">ATR trailing stop</option>
            </select>
          </div>
          {state.trailMode === "atr" && (
            <LiveSlider
              id="trail-atr"
              label="Trail ATR multiplier"
              value={state.trailAtrMultiplier}
              min={0.5}
              max={3}
              step={0.1}
              formatValue={(v) => v.toFixed(1)}
              onChange={(v) => onChange("trailAtrMultiplier", v)}
            />
          )}
          {state.trailMode === "ema_slow" && (
            <p className="param-helper">Trail stop follows the slow EMA from the crossover signal.</p>
          )}
        </>
      )}
    </ParameterCard>
  );
}
