import ParameterCard from "../ParameterCard";
import SegmentedControl from "../SegmentedControl";
import ParamToggleRow from "../ParamToggleRow";
import ParamHelpTip from "../ParamHelpTip";
import LiveSlider from "../LiveSlider";
import NumberStepper from "../NumberStepper";
import type { Confirmation, Direction } from "../../../../lib/strategyParams";

type SignalRulesSectionProps = {
  expanded: boolean;
  onToggle: () => void;
  direction: Direction;
  confirmation: Confirmation;
  onDirectionChange: (value: Direction) => void;
  onConfirmationChange: (value: Confirmation) => void;
  approachingEnabled?: boolean;
  approachingMaxGapAtr?: number;
  approachingMinNarrowBars?: number;
  onApproachingEnabledChange?: (value: boolean) => void;
  onApproachingMaxGapAtrChange?: (value: number) => void;
  onApproachingMinNarrowBarsChange?: (value: number) => void;
  showApproaching?: boolean;
};

export default function SignalRulesSection({
  expanded,
  onToggle,
  direction,
  confirmation,
  onDirectionChange,
  onConfirmationChange,
  approachingEnabled = true,
  approachingMaxGapAtr = 0.5,
  approachingMinNarrowBars = 2,
  onApproachingEnabledChange,
  onApproachingMaxGapAtrChange,
  onApproachingMinNarrowBarsChange,
  showApproaching = false,
}: SignalRulesSectionProps) {
  return (
    <ParameterCard title="Signal Rules" required expanded={expanded} onToggle={onToggle}>
      <SegmentedControl
        label="Direction"
        value={direction}
        options={[
          { value: "long", label: "Long" },
          { value: "short", label: "Short" },
          { value: "both", label: "Both" },
        ]}
        onChange={onDirectionChange}
      />
      <SegmentedControl
        label="Confirmation"
        value={confirmation}
        options={[
          { value: "close", label: "Close" },
          { value: "pullback", label: "Pullback" },
          { value: "aggressive", label: "Aggressive" },
        ]}
        onChange={onConfirmationChange}
      />

      {showApproaching && onApproachingEnabledChange && (
        <ParamToggleRow
          label="Approaching entries"
          checked={approachingEnabled}
          labelHelp={
            <ParamHelpTip
              label="Approaching entries"
              title="Approaching entries"
              body="When on, emit watch-only approaching signals when EMAs converge within a max ATR gap. These do not open trades by themselves; disable to require a completed close-confirmed crossover only."
            />
          }
          onChange={onApproachingEnabledChange}
        >
          <LiveSlider
            id="approaching-max-gap"
            label="Max gap (× ATR)"
            value={approachingMaxGapAtr}
            min={0.01}
            max={5}
            step={0.05}
            formatValue={(v) => v.toFixed(2)}
            onChange={(v) => onApproachingMaxGapAtrChange?.(v)}
          />
          <NumberStepper
            id="approaching-narrow-bars"
            label="Min narrowing bars"
            value={approachingMinNarrowBars}
            min={1}
            max={10}
            onChange={(v) => onApproachingMinNarrowBarsChange?.(v)}
          />
        </ParamToggleRow>
      )}
    </ParameterCard>
  );
}
