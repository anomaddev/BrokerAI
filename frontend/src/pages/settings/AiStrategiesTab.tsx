import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AiStrategySettings } from "../../api/client";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import ToggleSwitch from "../../components/ToggleSwitch";
import useAutoSave from "../../hooks/useAutoSave";

const DEFAULT_SETTINGS: AiStrategySettings = {
  startup_enabled: true,
  startup_loop_count: 3,
  startup_backtest_period: "6m",
  startup_timeout_minutes: 180,
};

const PERIOD_OPTIONS: { value: string; label: string }[] = [
  { value: "1m", label: "1 month" },
  { value: "3m", label: "3 months" },
  { value: "6m", label: "6 months" },
  { value: "1y", label: "1 year" },
  { value: "2y", label: "2 years" },
  { value: "5y", label: "5 years" },
];

const LOOP_OPTIONS = Array.from({ length: 10 }, (_, index) => index + 1);

export default function AiStrategiesTab() {
  const [settings, setSettings] = useState<AiStrategySettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  const { saveStatus, scheduleSave, markReady, markNotReady, error: saveError } = useAutoSave({
    onSave: async () => {
      const snapshot = settingsRef.current;
      const saved = await api.updateAiStrategySettings({
        startup_enabled: snapshot.startup_enabled,
        startup_loop_count: snapshot.startup_loop_count,
        startup_backtest_period: snapshot.startup_backtest_period,
        startup_timeout_minutes: snapshot.startup_timeout_minutes,
      });
      setSettings(saved);
      settingsRef.current = saved;
    },
    canSave: () => !loading,
  });

  useEffect(() => {
    let cancelled = false;
    markNotReady();
    void (async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const data = await api.getAiStrategySettings();
        if (!cancelled) {
          setSettings(data);
          settingsRef.current = data;
          markReady();
        }
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Failed to load AI Strategy settings");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      markNotReady();
    };
  }, [markNotReady, markReady]);

  function update(partial: Partial<AiStrategySettings>) {
    setSettings((current) => {
      const next = { ...current, ...partial };
      settingsRef.current = next;
      return next;
    });
    scheduleSave();
  }

  const saving = saveStatus === "saving";

  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title="AI Strategies"
        description="Configure the create-time startup sequence that seeds memory and runs improve loops for new AI Strategies."
        error={loadError || saveError}
        message={
          saveStatus === "saved"
            ? "Saved"
            : saveStatus === "saving"
              ? "Saving…"
              : saveStatus === "error"
                ? null
                : undefined
        }
      />
      <div className="settings-panel-body settings-panel-body--stack">
        {loading ? (
          <p className="settings-muted">Loading AI Strategy settings…</p>
        ) : (
          <>
            <section className="account-section-card">
              <div className="settings-section-intro">
                <div className="settings-section-intro-row">
                  <div>
                    <h3 className="settings-subsection-title">Startup sequence</h3>
                    <p className="settings-panel-desc">
                      When a new AI Strategy is created, BrokerAI can wait for required research
                      reports, seed a memory digest from that research, then run a configurable
                      number of compiled-playbook backtests with memory feedback — so the strategy
                      has more than candles and lookback before warm-up trading begins.
                    </p>
                  </div>
                </div>
              </div>

              <div className="general-settings-stack">
                <div className="general-settings-group">
                  <div className="research-source-row">
                    <div className="research-source-main">
                      <span className="research-source-name">Run startup on create</span>
                      <span className="settings-muted">
                        Off skips enqueueing the startup job when you create an AI Strategy.
                      </span>
                    </div>
                    <ToggleSwitch
                      label="Run startup on create"
                      checked={settings.startup_enabled}
                      disabled={saving}
                      onChange={(startup_enabled) => update({ startup_enabled })}
                    />
                  </div>

                  <label className="general-settings-field">
                    <span className="general-settings-field-label">Improve loops</span>
                    <div className="research-select-wrap">
                      <select
                        className="research-select"
                        disabled={saving || !settings.startup_enabled}
                        value={settings.startup_loop_count}
                        onChange={(event) =>
                          update({ startup_loop_count: Number(event.target.value) })
                        }
                      >
                        {LOOP_OPTIONS.map((count) => (
                          <option key={count} value={count}>
                            {count}
                          </option>
                        ))}
                      </select>
                    </div>
                    <span className="settings-field-hint">
                      Each loop runs one compiled-playbook backtest and applies memory feedback.
                    </span>
                  </label>

                  <label className="general-settings-field">
                    <span className="general-settings-field-label">Startup backtest period</span>
                    <div className="research-select-wrap">
                      <select
                        className="research-select"
                        disabled={saving || !settings.startup_enabled}
                        value={settings.startup_backtest_period || "6m"}
                        onChange={(event) =>
                          update({ startup_backtest_period: event.target.value })
                        }
                      >
                        {PERIOD_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </label>

                  <label className="general-settings-field">
                    <span className="general-settings-field-label">Timeout (minutes)</span>
                    <div className="research-select-wrap research-select-wrap--plain">
                      <input
                        className="research-select"
                        type="number"
                        min={15}
                        max={1440}
                        step={15}
                        disabled={saving || !settings.startup_enabled}
                        value={settings.startup_timeout_minutes}
                        onChange={(event) =>
                          update({
                            startup_timeout_minutes: Number(event.target.value) || 180,
                          })
                        }
                      />
                    </div>
                    <span className="settings-field-hint">
                      Fail the startup job if reports, seeding, or loops stall longer than this.
                    </span>
                  </label>
                </div>
              </div>
            </section>

            <section className="account-section-card">
              <div className="settings-section-intro">
                <h3 className="settings-subsection-title">Related settings</h3>
                <p className="settings-panel-desc">
                  Startup waits on research reports the strategy has enabled, and memory feedback
                  uses the Backtesting AI feedback model.
                </p>
              </div>
              <p className="settings-muted">
                <Link to="/settings/reports">Settings → Reports</Link> — schedules and models for
                daily / weekly research
              </p>
              <p className="settings-muted">
                <Link to="/settings/backtesting">Settings → Backtesting</Link> — AI feedback model
                and daily AI Strategy backtest cadence
              </p>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
