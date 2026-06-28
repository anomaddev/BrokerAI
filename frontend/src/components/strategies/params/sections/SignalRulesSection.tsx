import ParameterCard from "../ParameterCard";
import SegmentedControl from "../SegmentedControl";
import type { Confirmation, Direction } from "../../../../lib/strategyParams";

type SignalRulesSectionProps = {
  expanded: boolean;
  onToggle: () => void;
  direction: Direction;
  confirmation: Confirmation;
  onDirectionChange: (value: Direction) => void;
  onConfirmationChange: (value: Confirmation) => void;
};

export default function SignalRulesSection({
  expanded,
  onToggle,
  direction,
  confirmation,
  onDirectionChange,
  onConfirmationChange,
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
    </ParameterCard>
  );
}
