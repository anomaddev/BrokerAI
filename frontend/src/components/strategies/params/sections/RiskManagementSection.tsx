import ParameterCard from "../ParameterCard";
import ParamToggleRow from "../ParamToggleRow";
import ParamHelpTip from "../ParamHelpTip";
import ParamOptionList from "../ParamOptionList";
import LiveSlider from "../LiveSlider";
import NumberStepper from "../NumberStepper";
import {
  stopLossModeOptions,
  takeProfitModeOptions,
  trailModeOptions,
  type StopLossMode,
  type TakeProfitMode,
  type TrailMode,
} from "../../../../lib/strategyParams";

export type RiskManagementState = {
  riskPerTrade: number;
  stopLossEnabled: boolean;
  stopLossType: StopLossMode;
  slAtrMultiplier: number;
  slFixedPips: number;
  slFixedPipsJpy: number;
  slStructureLookback: number;
  takeProfitEnabled: boolean;
  takeProfitType: TakeProfitMode;
  riskRewardRatio: number;
  tpFixedPips: number;
  tpAtrMultiplier: number;
  trailMode: TrailMode;
  trailAtrMultiplier: number;
  reverseCrossoverEnabled: boolean;
  reverseCrossoverMinBarsAfterEntry: number;
  reverseCrossoverMinConfirmationBars: number;
  reverseCrossoverMinSeparationAtr: number;
};

type RiskManagementSectionProps = {
  expanded: boolean;
  onToggle: () => void;
  state: RiskManagementState;
  emaSignalActive: boolean;
  onChange: <K extends keyof RiskManagementState>(key: K, value: RiskManagementState[K]) => void;
};

const RISK_HELP = {
  riskPerTrade: {
    label: "Risk per trade %",
    title: "Risk per trade %",
    body: "Percent of account equity risked on each trade. Position size is derived from this value and the stop-loss distance when a stop is enabled.",
  },
  stopLoss: {
    label: "Stop loss",
    title: "Stop loss",
    body: "Places a protective exit if price moves against the position. Choose fixed pips, ATR-based distance, or structure (swing) levels.",
  },
  takeProfit: {
    label: "Take profit",
    title: "Take profit",
    body: "Defines how winning trades exit — fixed pips, a risk/reward multiple of the stop, ATR distance, reverse crossover, or a trailing stop.",
  },
  reverseCrossover: {
    label: "Reverse crossover exit",
    title: "Reverse crossover protection",
    body: "When take profit is reverse crossover, ignore early flips until min bars / confirmation / ATR separation are met. ATR stop loss remains the hard safety net.",
  },
} as const;

export default function RiskManagementSection({
  expanded,
  onToggle,
  state,
  emaSignalActive,
  onChange,
}: RiskManagementSectionProps) {
  const slOptions = stopLossModeOptions();
  const tpOptions = takeProfitModeOptions(emaSignalActive);
  const trailOptions = trailModeOptions(emaSignalActive);

  return (
    <ParameterCard
      className="parameter-card--risk"
      title="Risk Management"
      required
      expanded={expanded}
      onToggle={onToggle}
    >
      <LiveSlider
        id="risk-pct"
        label="Risk per trade %"
        labelHelp={
          <ParamHelpTip
            label={RISK_HELP.riskPerTrade.label}
            title={RISK_HELP.riskPerTrade.title}
            body={RISK_HELP.riskPerTrade.body}
          />
        }
        value={state.riskPerTrade}
        min={0.25}
        max={5}
        step={0.25}
        unit="%"
        onChange={(v) => onChange("riskPerTrade", v)}
      />

      <ParamToggleRow
        label="Stop loss"
        checked={state.stopLossEnabled}
        labelHelp={
          <ParamHelpTip
            label={RISK_HELP.stopLoss.label}
            title={RISK_HELP.stopLoss.title}
            body={RISK_HELP.stopLoss.body}
          />
        }
        onChange={(enabled) => onChange("stopLossEnabled", enabled)}
      >
        <ParamOptionList
          label="Stop Loss type"
          name="sl-type"
          value={state.stopLossType}
          options={slOptions}
          onChange={(value) => onChange("stopLossType", value)}
        />

        {state.stopLossType === "fixed_pips" && (
          <>
            <LiveSlider
              id="sl-pips"
              label="SL distance (pips)"
              value={state.slFixedPips}
              min={5}
              max={100}
              onChange={(v) => onChange("slFixedPips", v)}
            />
            <LiveSlider
              id="sl-pips-jpy"
              label="SL distance — JPY pairs (pips)"
              value={state.slFixedPipsJpy}
              min={5}
              max={150}
              onChange={(v) => onChange("slFixedPipsJpy", v)}
            />
            <p className="param-helper">
              JPY pip = 0.01. Used when the traded pair quotes in JPY (e.g. USD/JPY).
            </p>
          </>
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
      </ParamToggleRow>

      <ParamToggleRow
        label="Take profit"
        checked={state.takeProfitEnabled}
        labelHelp={
          <ParamHelpTip
            label={RISK_HELP.takeProfit.label}
            title={RISK_HELP.takeProfit.title}
            body={RISK_HELP.takeProfit.body}
          />
        }
        onChange={(enabled) => onChange("takeProfitEnabled", enabled)}
      >
        <ParamOptionList
          label="Take Profit type"
          name="tp-type"
          value={state.takeProfitType}
          options={tpOptions}
          onChange={(value) => onChange("takeProfitType", value)}
        />

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

        {state.takeProfitType === "trailing_stop" && (
          <>
            <ParamOptionList
              label="Trailing stop type"
              name="trail-mode"
              value={state.trailMode}
              options={trailOptions}
              onChange={(value) => onChange("trailMode", value)}
            />
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
          </>
        )}

        {state.takeProfitType === "reverse_crossover" && emaSignalActive && (
          <>
            <p className="param-helper">
              <ParamHelpTip
                label={RISK_HELP.reverseCrossover.label}
                title={RISK_HELP.reverseCrossover.title}
                body={RISK_HELP.reverseCrossover.body}
              />{" "}
              Early-trade protection for reverse-crossover exits:
            </p>
            <NumberStepper
              id="rc-min-bars"
              label="Min bars after entry"
              value={state.reverseCrossoverMinBarsAfterEntry}
              min={0}
              max={30}
              onChange={(v) => onChange("reverseCrossoverMinBarsAfterEntry", v)}
            />
            <p className="param-helper">Ignore reverse crosses in the first N bars after entry.</p>
            <NumberStepper
              id="rc-confirm-bars"
              label="Min confirmation bars"
              value={state.reverseCrossoverMinConfirmationBars}
              min={1}
              max={5}
              onChange={(v) => onChange("reverseCrossoverMinConfirmationBars", v)}
            />
            <p className="param-helper">Reverse EMA relationship must hold for this many bars.</p>
            <LiveSlider
              id="rc-separation"
              label="Min separation (× ATR)"
              value={state.reverseCrossoverMinSeparationAtr}
              min={0}
              max={1}
              step={0.05}
              formatValue={(v) => v.toFixed(2)}
              onChange={(v) => onChange("reverseCrossoverMinSeparationAtr", v)}
            />
            <p className="param-helper">Require EMAs to separate by this × ATR before exiting (0 disables).</p>
          </>
        )}
      </ParamToggleRow>
    </ParameterCard>
  );
}
