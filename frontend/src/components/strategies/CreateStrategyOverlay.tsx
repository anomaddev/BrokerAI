import { useState } from "react";
import { useNavigate } from "react-router-dom";
import StrategyOverlay from "./StrategyOverlay";
import StrategyModeStep from "./StrategyModeStep";
import StrategyPresetStep from "./StrategyPresetStep";

type CreateStep = "mode" | "preset";

type CreateStrategyOverlayProps = {
  onClose: () => void;
};

export default function CreateStrategyOverlay({ onClose }: CreateStrategyOverlayProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState<CreateStep>("mode");

  function handleSelectPreset(route: string) {
    onClose();
    navigate(route);
  }

  return (
    <StrategyOverlay
      onClose={onClose}
      wide
      titleId={step === "mode" ? "create-strategy-title" : "create-strategy-preset-title"}
    >
      {step === "mode" ? (
        <StrategyModeStep
          onSelectPreset={() => setStep("preset")}
          onSelectCustom={() => {
            onClose();
            navigate("/trading/strategies/new/custom");
          }}
          onCancel={onClose}
        />
      ) : (
        <StrategyPresetStep
          onSelect={handleSelectPreset}
          onBack={() => setStep("mode")}
          onCancel={onClose}
        />
      )}
    </StrategyOverlay>
  );
}
