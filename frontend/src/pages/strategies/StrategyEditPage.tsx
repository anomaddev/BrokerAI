import { useEffect, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { api, type Strategy } from "../../api/client";
import EmaCrossoverBuilder from "./presets/emaCrossover/EmaCrossoverBuilder";
import CustomBuilder from "./presets/custom/CustomBuilder";
import { v1ToEmaCrossoverParams } from "./presets/emaCrossover/apiParams";
import { v1ToCustomBuilderParams } from "./presets/custom/defaults";

export default function StrategyEditPage() {
  const { id } = useParams<{ id: string }>();
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const doc = await api.getStrategy(id);
        if (!cancelled) setStrategy(doc);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load strategy");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (!id) return <Navigate to="/trading/strategies" replace />;
  if (loading) return <div className="center-page">Loading strategy…</div>;
  if (error || !strategy) return <Navigate to="/trading/strategies" replace />;

  const commonProps = {
    editStrategyId: strategy.id,
    editName: strategy.name,
    editDescription: strategy.description,
    editInstrumentSelection: strategy.instrument_selection,
    editEnabled: strategy.enabled,
  };

  if (strategy.preset_id === "ema_crossover" && strategy.params) {
    return (
      <EmaCrossoverBuilder
        {...commonProps}
        initialParams={v1ToEmaCrossoverParams(strategy.params)}
      />
    );
  }

  if (strategy.preset_id === "custom" && strategy.params) {
    return (
      <CustomBuilder
        {...commonProps}
        initialParams={v1ToCustomBuilderParams(strategy.params)}
      />
    );
  }

  return <Navigate to="/trading/strategies" replace />;
}
