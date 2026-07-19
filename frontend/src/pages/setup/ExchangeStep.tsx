import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { api, type OandaConnection } from "../../api/client";
import ExchangeLogo from "../../components/ExchangeLogo";
import OandaConnectionOverlay from "../../components/OandaConnectionOverlay";
import {
  availableOnboardingModules,
  getOnboardingModule,
  onboardingExchangeCatalog,
} from "../../lib/onboardingExchanges";
import {
  getExchange,
  groupExchangesByAssetClass,
  type ExchangeId,
} from "../../lib/exchanges";

type ExchangeStepProps = {
  selectedExchangeId: string | null;
  onContinue: (exchangeId: ExchangeId) => void;
  onSkip: () => void;
  onBack: () => void;
};

const emptyOanda: OandaConnection = {
  exchange_id: "oanda",
  connected: false,
  environment: "practice",
  account_id: null,
  access_token: null,
  access_token_set: false,
};

export default function ExchangeStep({
  selectedExchangeId,
  onContinue,
  onSkip,
  onBack,
}: ExchangeStepProps) {
  const groups = groupExchangesByAssetClass(onboardingExchangeCatalog());
  const available = new Set(availableOnboardingModules().map((m) => m.id));

  const [addedIds, setAddedIds] = useState<ExchangeId[]>(() =>
    selectedExchangeId ? [selectedExchangeId as ExchangeId] : [],
  );
  const [pickerOpen, setPickerOpen] = useState(false);
  const [connectingId, setConnectingId] = useState<ExchangeId | null>(null);
  const [oandaConnection, setOandaConnection] = useState<OandaConnection>(emptyOanda);
  const [loadingConnection, setLoadingConnection] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const conn = await api.getOandaConnection();
        if (cancelled) return;
        setOandaConnection(conn);
        if (conn.connected) {
          setAddedIds((current) =>
            current.includes("oanda") ? current : [...current, "oanda"],
          );
        }
      } catch {
        // Preview / offline: keep empty list.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const addedExchanges = addedIds
    .map((id) => getExchange(id))
    .filter((exchange): exchange is NonNullable<typeof exchange> => Boolean(exchange));
  const hasExchange = addedExchanges.length > 0;
  const addedSet = new Set(addedIds);

  async function openConnect(exchangeId: ExchangeId) {
    if (!available.has(exchangeId)) return;
    setError("");
    setPickerOpen(false);

    if (exchangeId === "oanda") {
      setLoadingConnection(true);
      setConnectingId("oanda");
      try {
        const conn = await api.getOandaConnection();
        setOandaConnection(conn);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load connection");
        setConnectingId(null);
      } finally {
        setLoadingConnection(false);
      }
      return;
    }

    const module = getOnboardingModule(exchangeId);
    if (!module) {
      setError("This exchange is not available yet.");
    }
  }

  async function removeExchange(exchangeId: ExchangeId) {
    setError("");
    setBusy(true);
    try {
      if (exchangeId === "oanda" && oandaConnection.connected) {
        await api.deleteOandaConnection();
        setOandaConnection(emptyOanda);
      }
      setAddedIds((current) => current.filter((id) => id !== exchangeId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove exchange");
    } finally {
      setBusy(false);
    }
  }

  function handlePrimary() {
    if (!hasExchange) {
      onSkip();
      return;
    }
    const primary = addedIds[0];
    if (primary) onContinue(primary);
  }

  return (
    <div className="onboarding-welcome onboarding-welcome--exchange">
      <div className="onboarding-welcome-main">
        <div className="onboarding-welcome-copy">
          <h1>Connect an exchange</h1>
          <p>Optional — add a broker now, or skip and connect later in Settings.</p>
        </div>

        {error && <div className="error">{error}</div>}

        <div className="onboarding-exchange-tray">
          {addedExchanges.length === 0 ? (
            <p className="onboarding-exchange-tray-empty">No exchanges added yet</p>
          ) : (
            <ul className="onboarding-exchange-tray-list">
              {addedExchanges.map((exchange) => (
                <li key={exchange.id} className="onboarding-exchange-tray-item">
                  <ExchangeLogo exchange={exchange} size={32} />
                  <div className="onboarding-exchange-tray-item-text">
                    <strong>{exchange.name}</strong>
                    <span>{exchange.category}</span>
                  </div>
                  <button
                    type="button"
                    className="onboarding-exchange-tray-remove"
                    aria-label={`Remove ${exchange.name}`}
                    disabled={busy}
                    onClick={() => void removeExchange(exchange.id)}
                  >
                    <X size={16} strokeWidth={2} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <button
            type="button"
            className="onboarding-exchange-add"
            onClick={() => setPickerOpen(true)}
            disabled={busy || loadingConnection}
            aria-label="Add exchange"
          >
            <Plus size={22} strokeWidth={2.25} />
            <span>Add exchange</span>
          </button>
        </div>
      </div>

      <div className="onboarding-welcome-actions">
        <button
          type="button"
          className="btn btn-secondary onboarding-welcome-cta"
          onClick={onBack}
          disabled={busy || loadingConnection}
        >
          Back
        </button>
        <button
          type="button"
          className="btn onboarding-welcome-cta"
          onClick={handlePrimary}
          disabled={busy || loadingConnection}
        >
          {hasExchange ? "Continue" : "Skip for now"}
        </button>
      </div>

      {pickerOpen && (
        <div
          className="onboarding-nested-overlay"
          role="presentation"
          onClick={() => setPickerOpen(false)}
        >
          <div
            className="onboarding-nested-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="onboarding-exchange-picker-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="onboarding-welcome-copy">
              <h1 id="onboarding-exchange-picker-title">Add an exchange</h1>
              <p>Choose a broker to connect. More options will appear as modules ship.</p>
            </div>

            <div className="onboarding-exchange-groups">
              {groups.map((group) => (
                <section key={group.assetClass} className="onboarding-exchange-group">
                  <h3 className="onboarding-exchange-group-title">{group.label}</h3>
                  <div className="onboarding-exchange-grid">
                    {group.exchanges.map((exchange) => {
                      const isAvailable = available.has(exchange.id);
                      const alreadyAdded = addedSet.has(exchange.id);
                      const disabled = !isAvailable || alreadyAdded || busy;
                      return (
                        <button
                          key={exchange.id}
                          type="button"
                          className={`onboarding-exchange-card${
                            !isAvailable || alreadyAdded ? " is-disabled" : ""
                          }`}
                          disabled={disabled}
                          onClick={() => void openConnect(exchange.id)}
                        >
                          <ExchangeLogo exchange={exchange} size={36} />
                          <div className="onboarding-exchange-card-text">
                            <strong>{exchange.name}</strong>
                            <span>{exchange.category}</span>
                            {alreadyAdded ? (
                              <em>Added</em>
                            ) : !isAvailable ? (
                              <em>Coming soon</em>
                            ) : null}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>

            <div className="onboarding-welcome-actions">
              <button
                type="button"
                className="btn btn-secondary onboarding-welcome-cta"
                onClick={() => setPickerOpen(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {connectingId === "oanda" && !loadingConnection && (
        <OandaConnectionOverlay
          connection={oandaConnection}
          onClose={() => setConnectingId(null)}
          onSaved={(saved) => {
            setOandaConnection(saved);
            setConnectingId(null);
            if (saved.connected) {
              setAddedIds((current) =>
                current.includes("oanda") ? current : [...current, "oanda"],
              );
            }
          }}
        />
      )}
    </div>
  );
}
