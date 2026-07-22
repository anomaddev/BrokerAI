import { useEffect, useState } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";
import { api, type Strategy } from "../../api/client";
import { ROUTES } from "../../lib/routes";
import { clearBacktestAiDraft, loadBacktestAiDraft } from "../../lib/backtests/applyAiSuggestions";
import EmaCrossoverBuilder from "./presets/emaCrossover/EmaCrossoverBuilder";
import CustomBuilder from "./presets/custom/CustomBuilder";
import AiStrategyBuilder from "./presets/aiStrategy/AiStrategyBuilder";
import { v1ToEmaCrossoverParams } from "./presets/emaCrossover/apiParams";
import { v1ToCustomBuilderParams } from "./presets/custom/defaults";
import { v1ToAiStrategyParams } from "./presets/aiStrategy/apiParams";

export default function StrategyEditPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const fromBacktest = searchParams.get("fromBacktest");
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draftBanner, setDraftBanner] = useState<string | null>(null);
  const [draftParams, setDraftParams] = useState<Strategy["params"] | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const doc = await api.getStrategy(id);
        if (cancelled) return;

        if (fromBacktest) {
          const draft = loadBacktestAiDraft(fromBacktest);
          if (draft && draft.strategyId === id) {
            setDraftParams(draft.params);
            setDraftBanner(
              "Draft from backtest AI suggestions — review the highlighted settings before saving.",
            );
            clearBacktestAiDraft(fromBacktest);
          }
        }

        setStrategy(doc);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load strategy");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, fromBacktest]);

  if (!id) return <Navigate to={ROUTES.research.strategies} replace />;
  if (loading) return <div className="center-page">Loading strategy…</div>;
  if (error || !strategy) return <Navigate to={ROUTES.research.strategies} replace />;

  const params = draftParams ?? strategy.params;

  const commonProps = {
    editStrategyId: strategy.id,
    editName: strategy.name,
    editDescription: strategy.description,
    editInstrumentSelection: strategy.instrument_selection,
    editEnabled: strategy.enabled,
  };

  const banner = draftBanner ? (
    <div className="strategy-builder-ai-draft-banner" role="status">
      {draftBanner}
    </div>
  ) : null;

  if (strategy.preset_id === "ema_crossover" && params) {
    return (
      <>
        {banner}
        <EmaCrossoverBuilder
          {...commonProps}
          initialParams={v1ToEmaCrossoverParams(params)}
          initialParamsV1={params}
        />
      </>
    );
  }

  if (strategy.preset_id === "custom" && params) {
    return (
      <>
        {banner}
        <CustomBuilder
          {...commonProps}
          initialParams={v1ToCustomBuilderParams(params)}
          initialParamsV1={params}
        />
      </>
    );
  }

  if (strategy.preset_id === "ai_strategy" && params) {
    return (
      <>
        {banner}
        <AiStrategyBuilder
          {...commonProps}
          initialParams={v1ToAiStrategyParams(params)}
          initialParamsV1={params}
        />
      </>
    );
  }

  return <Navigate to={ROUTES.research.strategies} replace />;
}
