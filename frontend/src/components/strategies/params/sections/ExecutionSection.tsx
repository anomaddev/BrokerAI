import ParameterCard from "../ParameterCard";
import LiveSlider from "../LiveSlider";
import NumberStepper from "../NumberStepper";
import ParamToggleRow from "../ParamToggleRow";

type ExecutionSectionProps = {
  expanded: boolean;
  onToggle: () => void;
  minConfidence: number;
  maxTradesPerDay: number;
  overrideAllStrategies: boolean;
  priority: number;
  onMinConfidenceChange: (value: number) => void;
  onMaxTradesChange: (value: number) => void;
  onOverrideChange: (value: boolean) => void;
  onPriorityChange: (value: number) => void;
};

export default function ExecutionSection({
  expanded,
  onToggle,
  minConfidence,
  maxTradesPerDay,
  overrideAllStrategies,
  priority,
  onMinConfidenceChange,
  onMaxTradesChange,
  onOverrideChange,
  onPriorityChange,
}: ExecutionSectionProps) {
  return (
    <ParameterCard title="Execution" required expanded={expanded} onToggle={onToggle}>
      <LiveSlider
        id="min-confidence"
        label="Min confidence threshold"
        value={minConfidence}
        min={0}
        max={100}
        unit="%"
        onChange={onMinConfidenceChange}
      />
      <NumberStepper
        id="max-trades"
        label="Max trades per day, per symbol"
        value={maxTradesPerDay}
        min={1}
        max={20}
        showButtons
        onChange={onMaxTradesChange}
      />
      <ParamToggleRow
        label="Override all other strategies"
        checked={overrideAllStrategies}
        onChange={onOverrideChange}
      />
      <LiveSlider
        id="priority"
        label="Priority (lower = higher priority)"
        value={priority}
        min={0}
        max={100}
        onChange={onPriorityChange}
      />
    </ParameterCard>
  );
}
