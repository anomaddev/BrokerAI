import { useNavigate } from "react-router-dom";
import StrategyOverlay from "./StrategyOverlay";
import StrategyPresetStep from "./StrategyPresetStep";

type CreateStrategyOverlayProps = {
  onClose: () => void;
};

export default function CreateStrategyOverlay({ onClose }: CreateStrategyOverlayProps) {
  const navigate = useNavigate();

  function handleSelectPreset(route: string) {
    onClose();
    navigate(route);
  }

  return (
    <StrategyOverlay onClose={onClose} wide titleId="create-strategy-preset-title">
      <StrategyPresetStep onSelect={handleSelectPreset} onCancel={onClose} />
    </StrategyOverlay>
  );
}
