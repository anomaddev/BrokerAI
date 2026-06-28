import { Navigate, useParams } from "react-router-dom";
import { getPresetByRouteSlug } from "./presets";
import EmaCrossoverBuilder from "./presets/emaCrossover/EmaCrossoverBuilder";
import CustomBuilder from "./presets/custom/CustomBuilder";

export default function StrategyBuilderPage() {
  const { presetId } = useParams<{ presetId: string }>();
  const preset = presetId ? getPresetByRouteSlug(presetId) : undefined;

  if (!preset) {
    return <Navigate to="/trading/strategies" replace />;
  }

  switch (preset.id) {
    case "ema_crossover":
      return <EmaCrossoverBuilder />;
    case "custom":
      return <CustomBuilder />;
    default:
      return <Navigate to="/trading/strategies" replace />;
  }
}
