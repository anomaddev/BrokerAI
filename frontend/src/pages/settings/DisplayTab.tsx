import { useEffect, useRef, useState } from "react";
import { api, type MarketIndicators } from "../../api/client";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import useAutoSave from "../../hooks/useAutoSave";
import { useGeneralSettings } from "../../hooks/useGeneralSettings";
import {
  DEFAULT_MARKET_INDICATORS,
  normalizeMarketIndicators,
  notifyDisplaySettingsUpdated,
} from "../../lib/displaySettings";
import { MARKET_SESSION_DEFS } from "../../lib/marketSessions";

export default function DisplayTab() {
  const { formatSessionHours } = useGeneralSettings();
  const [indicators, setIndicators] = useState<MarketIndicators>(DEFAULT_MARKET_INDICATORS);
  const [loading, setLoading] = useState(true);
  const indicatorsRef = useRef(indicators);

  indicatorsRef.current = indicators;

  const { saving, saveStatus, error, scheduleSave, markReady, markNotReady } = useAutoSave({
    onSave: async () => {
      const saved = await api.updateDisplaySettings({
        market_indicators: indicatorsRef.current,
      });
      setIndicators(normalizeMarketIndicators(saved.market_indicators));
      notifyDisplaySettingsUpdated();
    },
  });

  useEffect(() => {
    let cancelled = false;

    api
      .getDisplaySettings()
      .then((data) => {
        if (cancelled) return;
        setIndicators(normalizeMarketIndicators(data.market_indicators));
        markReady();
      })
      .catch(() => {
        if (!cancelled) {
          setIndicators(DEFAULT_MARKET_INDICATORS);
          markReady();
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      markNotReady();
    };
  }, [markNotReady, markReady]);

  function toggleIndicator(sessionId: string, enabled: boolean) {
    setIndicators((current) => {
      const next = { ...current, [sessionId]: enabled };
      indicatorsRef.current = next;
      return next;
    });
    scheduleSave();
  }

  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title="Display"
        description="Choose what appears in the BrokerAI header and navigation."
      />
      <div className="settings-panel-body settings-panel-body--stack">
        {loading ? (
          <p className="settings-muted">Loading display settings…</p>
        ) : (
          <section className="account-section-card">
            <div className="settings-section-intro">
              <div className="settings-section-intro-row">
                <div>
                  <h3 className="settings-subsection-title">Show market indicators</h3>
                  <p className="settings-panel-desc">
                    Trading session pills in the top bar show whether Asia, London, and NY sessions
                    are open. Requires a configured Massive connection.
                  </p>
                </div>
                {saveStatus === "saving" ? (
                  <span className="settings-save-status">Saving…</span>
                ) : saveStatus === "saved" ? (
                  <span className="settings-save-status settings-save-status--saved">Saved</span>
                ) : null}
              </div>
            </div>

            {error ? <p className="settings-error">{error}</p> : null}

            <div
              className="forex-pairs-grid"
              style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}
            >
              {MARKET_SESSION_DEFS.map((session) => {
                const checked = indicators[session.id] ?? true;
                return (
                  <label
                    key={session.id}
                    className={`forex-pair-checkbox${checked ? " forex-pair-checkbox--checked" : ""}`}
                    title={formatSessionHours(session)}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={saving}
                      onChange={(e) => toggleIndicator(session.id, e.target.checked)}
                    />
                    <span className="forex-pair-label">{session.name}</span>
                  </label>
                );
              })}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
