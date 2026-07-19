import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { DEFAULT_ONBOARDING_PAIRS } from "../../lib/onboardingSteps";
import { getOnboardingModule } from "../../lib/onboardingExchanges";
import type { ExchangeId } from "../../lib/exchanges";
type InstrumentsStepProps = {
  exchangeId: string | null;
  initialPairs: string[] | null;
  onSaved: (pairs: string[]) => void;
  onBack: () => void;
};

export default function InstrumentsStep({
  exchangeId,
  initialPairs,
  onSaved,
  onBack,
}: InstrumentsStepProps) {
  const module = getOnboardingModule(exchangeId as ExchangeId | null);
  const [catalog, setCatalog] = useState<string[]>([]);
  const [pairOrder, setPairOrder] = useState<string[]>([]);
  const [enabledPairs, setEnabledPairs] = useState<string[]>(
    initialPairs?.length ? initialPairs : DEFAULT_ONBOARDING_PAIRS,
  );
  const [sessions, setSessions] = useState<Record<string, boolean>>({});
  const [onlyOne, setOnlyOne] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const forex = await api.getForexPairs();
        if (cancelled) return;
        setCatalog(forex.catalog);
        setPairOrder(forex.pair_order.length ? forex.pair_order : forex.catalog);
        setSessions(forex.enabled_sessions);
        setOnlyOne(forex.only_one_position_per_pair);
        if (initialPairs?.length) {
          setEnabledPairs(initialPairs);
        } else if (forex.enabled_pairs.length) {
          setEnabledPairs(forex.enabled_pairs);
        } else {
          setEnabledPairs(
            DEFAULT_ONBOARDING_PAIRS.filter((pair) => forex.catalog.includes(pair)),
          );
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load pairs");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initialPairs]);

  async function handleContinue() {
    if (!exchangeId || enabledPairs.length === 0) {
      setError("Enable at least one instrument to continue");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.saveAssetSettings("forex", {
        // Connected during setup, but trading stays off until enabled in Settings.
        enabled: false,
        enabled_pairs: enabledPairs,
        pair_order: pairOrder,
        enabled_sessions: sessions,
        only_one_position_per_pair: onlyOne,
        primary_exchange: exchangeId,
      });
      onSaved(enabledPairs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save instruments");
    } finally {
      setSaving(false);
    }
  }

  if (!module) {
    return (
      <div className="onboarding-welcome onboarding-welcome--instruments">
        <div className="onboarding-welcome-main">
          <div className="onboarding-welcome-copy">
            <h1>Choose instruments</h1>
            <p>Select an exchange before choosing instruments.</p>
          </div>
          {error && <div className="error">{error}</div>}
        </div>
        <div className="onboarding-welcome-actions">
          <button type="button" className="btn btn-secondary onboarding-welcome-cta" onClick={onBack}>
            Back
          </button>
        </div>
      </div>
    );
  }

  const Instruments = module.InstrumentsStep;

  return (
    <div className="onboarding-welcome onboarding-welcome--instruments">
      <div className="onboarding-welcome-main">
        <div className="onboarding-welcome-copy">
          <h1>Choose instruments</h1>
          <p>
            Pick the forex pairs to connect. Trading stays off until you enable Forex under Settings
            → Broker.
          </p>
        </div>

        {error && <div className="error">{error}</div>}

        <div className="onboarding-instruments-block">
          <div className="onboarding-instruments-toolbar">
            <button
              type="button"
              className="onboarding-instruments-link"
              onClick={() => {
                const pairs = [...catalog].sort((a, b) => a.localeCompare(b));
                setEnabledPairs(pairs);
                setPairOrder(pairs);
              }}
              disabled={
                saving ||
                loading ||
                catalog.length === 0 ||
                (catalog.length > 0 &&
                  catalog.every((pair) => enabledPairs.includes(pair)))
              }
            >
              Select all
            </button>
            <button
              type="button"
              className="onboarding-instruments-link"
              onClick={() => {
                const pairs = [...catalog].sort((a, b) => a.localeCompare(b));
                setEnabledPairs([]);
                setPairOrder(pairs);
              }}
              disabled={saving || loading || enabledPairs.length === 0}
            >
              Clear all
            </button>
          </div>
          <div className="onboarding-instruments-tray">
            {loading ? (
              <p className="onboarding-instruments-tray-empty">Loading instruments…</p>
            ) : (
              <Instruments
                enabledPairs={enabledPairs}
                pairOrder={pairOrder}
                catalog={catalog}
                onEnabledPairsChange={setEnabledPairs}
                onPairOrderChange={setPairOrder}
                disabled={saving}
              />
            )}
          </div>
        </div>
      </div>

      <div className="onboarding-welcome-actions">
        <button
          type="button"
          className="btn btn-secondary onboarding-welcome-cta"
          onClick={onBack}
          disabled={saving}
        >
          Back
        </button>
        <button
          type="button"
          className="btn onboarding-welcome-cta"
          onClick={() => void handleContinue()}
          disabled={saving || loading || enabledPairs.length === 0}
        >
          {saving ? "Saving…" : "Continue"}
        </button>
      </div>
    </div>
  );
}
