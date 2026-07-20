import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type AiModel,
  type BacktestSettings,
  type ReasoningEffort,
} from "../../api/client";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import ToggleSwitch from "../../components/ToggleSwitch";
import useAutoSave from "../../hooks/useAutoSave";
import {
  catalogSelectionKey,
  parseCatalogSelectionKey,
  providerLabel,
} from "./modelProviders";

const DEFAULT_SETTINGS: BacktestSettings = {
  max_concurrent: 2,
  auto_start: true,
  ai_feedback_enabled: false,
  ai_feedback_auto_on_complete: false,
  ai_feedback_model_id: null,
  ai_feedback_model_name: null,
  ai_feedback_reasoning_effort: "medium",
};

const REASONING_OPTIONS: { value: ReasoningEffort; label: string }[] = [
  { value: "none", label: "None" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

type CatalogOption = {
  key: string;
  sourceId: string;
  modelName: string;
  label: string;
  sourceEnabled: boolean;
};

export default function BacktestingTab() {
  const [settings, setSettings] = useState<BacktestSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [models, setModels] = useState<AiModel[]>([]);
  const [catalog, setCatalog] = useState<CatalogOption[]>([]);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  const { saving, saveStatus, error, scheduleSave, markReady, markNotReady } = useAutoSave({
    onSave: async () => {
      const saved = await api.updateBacktestSettings(settingsRef.current);
      setSettings(saved);
    },
  });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [data, modelsRes] = await Promise.all([
          api.getBacktestSettings(),
          api.listModels(),
        ]);
        if (cancelled) return;
        setSettings({ ...DEFAULT_SETTINGS, ...data });
        setModels(modelsRes.models ?? []);
        markReady();
      } catch {
        if (!cancelled) {
          setSettings(DEFAULT_SETTINGS);
          markReady();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
      markNotReady();
    };
  }, [markNotReady, markReady]);

  useEffect(() => {
    let cancelled = false;
    async function loadCatalog() {
      const enabledSources = models.filter((m) => m.enabled);
      const options: CatalogOption[] = [];
      await Promise.all(
        enabledSources.map(async (source) => {
          try {
            const response = await api.listAvailableModels(source.id);
            const listed = response.models ?? [];
            if (listed.length === 0) {
              const fallback = source.default_model_name || source.model_name;
              if (fallback) {
                options.push({
                  key: catalogSelectionKey(source.id, fallback),
                  sourceId: source.id,
                  modelName: fallback,
                  label: `${providerLabel(source.type)} · ${fallback}`,
                  sourceEnabled: true,
                });
              }
              return;
            }
            for (const model of listed) {
              const name = model.id || model.name;
              if (!name) continue;
              options.push({
                key: catalogSelectionKey(source.id, name),
                sourceId: source.id,
                modelName: name,
                label: `${providerLabel(source.type)} · ${model.name || name}`,
                sourceEnabled: true,
              });
            }
          } catch {
            const fallback = source.default_model_name || source.model_name;
            if (fallback) {
              options.push({
                key: catalogSelectionKey(source.id, fallback),
                sourceId: source.id,
                modelName: fallback,
                label: `${providerLabel(source.type)} · ${fallback}`,
                sourceEnabled: true,
              });
            }
          }
        }),
      );
      if (!cancelled) setCatalog(options);
    }
    void loadCatalog();
    return () => {
      cancelled = true;
    };
  }, [models]);

  const selectedKey = useMemo(() => {
    if (!settings.ai_feedback_model_id || !settings.ai_feedback_model_name) return "";
    return catalogSelectionKey(settings.ai_feedback_model_id, settings.ai_feedback_model_name);
  }, [settings.ai_feedback_model_id, settings.ai_feedback_model_name]);

  function update(partial: Partial<BacktestSettings>) {
    setSettings((current) => {
      const next = { ...current, ...partial };
      settingsRef.current = next;
      return next;
    });
    scheduleSave();
  }

  const enabledSources = models.filter((m) => m.enabled);
  const feedbackDisabled = !settings.ai_feedback_enabled;

  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title="Backtesting"
        description="Control how many backtests can run at once and whether queued jobs start automatically."
      />
      <div className="settings-panel-body settings-panel-body--stack">
        {loading ? (
          <p className="settings-muted">Loading backtest settings…</p>
        ) : (
          <>
            <section className="account-section-card">
              <div className="settings-section-intro">
                <div className="settings-section-intro-row">
                  <div>
                    <h3 className="settings-subsection-title">Processor</h3>
                    <p className="settings-panel-desc">
                      Parallel workers share a process pool. Changes apply on the next claim cycle.
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

              <div className="general-settings-stack">
                <div className="general-settings-group">
                  <label className="general-settings-field">
                    <span className="general-settings-field-label">Max concurrent</span>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      disabled={saving}
                      value={settings.max_concurrent}
                      onChange={(event) => {
                        const value = Number(event.target.value);
                        if (!Number.isFinite(value)) return;
                        update({ max_concurrent: Math.max(1, Math.min(10, Math.round(value))) });
                      }}
                    />
                    <span className="settings-field-hint">Between 1 and 10. Default is 2.</span>
                  </label>

                  <div className="research-source-row">
                    <div className="research-source-main">
                      <span className="research-source-name">Auto start</span>
                      <span className="settings-muted">
                        When on, queued backtests start as soon as a worker is free. When off, you
                        must start each run from the Backtesting page.
                      </span>
                    </div>
                    <ToggleSwitch
                      label="Auto start"
                      checked={settings.auto_start}
                      disabled={saving}
                      onChange={(auto_start) => update({ auto_start })}
                    />
                  </div>
                </div>
              </div>
            </section>

            <section className="account-section-card">
              <div className="settings-section-intro">
                <div className="settings-section-intro-row">
                  <div>
                    <h3 className="settings-subsection-title">AI feedback</h3>
                    <p className="settings-panel-desc">
                      After a backtest completes, send a compact package of results to an enabled
                      model for strategy improvement suggestions.
                    </p>
                  </div>
                </div>
              </div>

              <div className="general-settings-stack">
                <div className="general-settings-group">
                  <div className="research-source-row">
                    <div className="research-source-main">
                      <span className="research-source-name">Enable AI feedback</span>
                      <span className="settings-muted">
                        Master switch for Analyze with AI on completed runs.
                      </span>
                    </div>
                    <ToggleSwitch
                      label="Enable AI feedback"
                      checked={settings.ai_feedback_enabled}
                      disabled={saving}
                      onChange={(ai_feedback_enabled) => update({ ai_feedback_enabled })}
                    />
                  </div>

                  <div className="research-source-row">
                    <div className="research-source-main">
                      <span className="research-source-name">Auto-analyze on complete</span>
                      <span className="settings-muted">
                        When on, feedback starts automatically after a successful backtest.
                      </span>
                    </div>
                    <ToggleSwitch
                      label="Auto-analyze on complete"
                      checked={settings.ai_feedback_auto_on_complete}
                      disabled={saving || feedbackDisabled}
                      onChange={(ai_feedback_auto_on_complete) =>
                        update({ ai_feedback_auto_on_complete })
                      }
                    />
                  </div>

                  <label className="general-settings-field">
                    <span className="general-settings-field-label">Model</span>
                    <div className="research-select-wrap">
                      <select
                        className="research-select"
                        disabled={saving || feedbackDisabled || catalog.length === 0}
                        value={selectedKey}
                        onChange={(event) => {
                          const parsed = parseCatalogSelectionKey(event.target.value);
                          if (!parsed) {
                            update({
                              ai_feedback_model_id: null,
                              ai_feedback_model_name: null,
                            });
                            return;
                          }
                          update({
                            ai_feedback_model_id: parsed.sourceId,
                            ai_feedback_model_name: parsed.modelName,
                          });
                        }}
                      >
                        <option value="">Select a model…</option>
                        {catalog.map((option) => (
                          <option key={option.key} value={option.key}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    {enabledSources.length === 0 ? (
                      <span className="settings-field-hint">
                        No enabled API sources. Connect one in{" "}
                        <Link to="/settings/models">Settings → Models</Link>.
                      </span>
                    ) : (
                      <span className="settings-field-hint">
                        Uses enabled sources from Settings → Models.
                      </span>
                    )}
                  </label>

                  <label className="general-settings-field">
                    <span className="general-settings-field-label">Reasoning effort</span>
                    <div className="research-select-wrap">
                      <select
                        className="research-select"
                        disabled={saving || feedbackDisabled}
                        value={settings.ai_feedback_reasoning_effort}
                        onChange={(event) =>
                          update({
                            ai_feedback_reasoning_effort: event.target.value as ReasoningEffort,
                          })
                        }
                      >
                        {REASONING_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </label>
                </div>
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
