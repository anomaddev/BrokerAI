import { Navigate, useParams } from "react-router-dom";
import { ROUTES } from "../../lib/routes";
import { getPresetByRouteSlug } from "./presets";
import EmaCrossoverBuilder from "./presets/emaCrossover/EmaCrossoverBuilder";
import CustomBuilder from "./presets/custom/CustomBuilder";
import AiStrategyBuilder from "./presets/aiStrategy/AiStrategyBuilder";

export default function StrategyBuilderPage() {
  const { presetId } = useParams<{ presetId: string }>();
  const preset = presetId ? getPresetByRouteSlug(presetId) : undefined;

  if (!preset) {
    return <Navigate to={ROUTES.research.strategies} replace />;
  }

  switch (preset.id) {
    case "ema_crossover":
      return <EmaCrossoverBuilder />;
    case "custom":
      return <CustomBuilder />;
    case "ai_strategy":
      return <AiStrategyBuilder />;
    default:
      return <Navigate to={ROUTES.research.strategies} replace />;
  }
}
