import { useEffect, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { api, type AiModel, type ModelProviderType } from "../../api/client";
import {
  getProvider,
  MODEL_PROVIDERS,
  providerLabel,
  type ModelProvider,
} from "../settings/modelProviders";

type ModelsStepProps = {
  onContinue: () => void;
  onSkip: () => void;
  onBack: () => void;
};

const EMPTY_FORM = {
  base_url: "",
  api_key: "",
};

export default function ModelsStep({ onContinue, onSkip, onBack }: ModelsStepProps) {
  const [models, setModels] = useState<AiModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [selectedType, setSelectedType] = useState<ModelProviderType | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  const connectedTypes = useMemo(
    () => new Set(models.map((model) => model.type)),
    [models],
  );
  const availableProviders = useMemo(
    () => MODEL_PROVIDERS.filter((item) => !connectedTypes.has(item.type)),
    [connectedTypes],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await api.listModels();
        if (!cancelled) setModels(data.models);
      } catch {
        // Preview / offline: keep empty tray.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const hasModel = models.length > 0;
  const provider = selectedType ? getProvider(selectedType) : undefined;

  function openPicker() {
    setError("");
    setMessage("");
    setPickerOpen(true);
  }

  function selectProvider(type: ModelProviderType) {
    const next = getProvider(type);
    if (!next) return;
    setSelectedType(type);
    setForm({
      base_url: next.defaults.base_url,
      api_key: "",
    });
    setMessage("");
    setError("");
    setPickerOpen(false);
    setConnecting(true);
  }

  function closeConnect() {
    if (saving || testing) return;
    setConnecting(false);
    setSelectedType(null);
    setForm(EMPTY_FORM);
    setMessage("");
  }

  async function removeModel(model: AiModel) {
    setError("");
    setBusy(true);
    try {
      await api.deleteModel(model.id);
      setModels((current) => current.filter((entry) => entry.id !== model.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove model");
    } finally {
      setBusy(false);
    }
  }

  async function persistNewModel() {
    if (!selectedType) return;
    const created = await api.createModel({
      title: getProvider(selectedType)?.defaults.title || providerLabel(selectedType),
      type: selectedType,
      base_url: form.base_url,
      api_key: form.api_key,
      enabled: true,
    });
    setModels((current) => [...current, created]);
    setConnecting(false);
    setSelectedType(null);
    setForm(EMPTY_FORM);
    setMessage("");
  }

  async function handleTestAndSave() {
    if (!selectedType || !provider) return;
    setTesting(true);
    setMessage("");
    setError("");
    try {
      if (provider.supportsConnectionTest) {
        const result = await api.testModelConnection({
          title: provider.defaults.title || providerLabel(selectedType),
          type: selectedType,
          base_url: form.base_url,
          api_key: form.api_key,
        });
        if (!result.ok) {
          setMessage(result.message);
          return;
        }
        setMessage(result.message);
      }

      setSaving(true);
      try {
        await persistNewModel();
      } finally {
        setSaving(false);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to connect model");
    } finally {
      setTesting(false);
    }
  }

  async function handleSaveWithoutTest() {
    if (!selectedType || !provider) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await persistNewModel();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save model");
    } finally {
      setSaving(false);
    }
  }

  function handlePrimary() {
    if (hasModel) onContinue();
    else onSkip();
  }

  const canSubmit =
    (provider?.apiKeyOnly || Boolean(form.base_url.trim())) &&
    (!provider?.apiKeyRequired || Boolean(form.api_key.trim()));

  return (
    <div className="onboarding-welcome onboarding-welcome--exchange">
      <div className="onboarding-welcome-main">
        <div className="onboarding-welcome-copy">
          <h1>Connect AI models</h1>
          <p>Optional — add an API source now, or skip and configure later in Settings.</p>
        </div>

        {error && <div className="error">{error}</div>}

        <div className="onboarding-exchange-tray">
          {loading ? (
            <p className="onboarding-exchange-tray-empty">Loading…</p>
          ) : models.length === 0 ? (
            <p className="onboarding-exchange-tray-empty">No providers added yet</p>
          ) : (
            <ul className="onboarding-exchange-tray-list">
              {models.map((model) => {
                const modelProvider = getProvider(model.type);
                return (
                  <li key={model.id} className="onboarding-exchange-tray-item">
                    {modelProvider ? (
                      <img
                        src={modelProvider.logo}
                        alt=""
                        width={32}
                        height={32}
                        className="onboarding-model-logo"
                      />
                    ) : null}
                    <div className="onboarding-exchange-tray-item-text">
                      <strong>{model.title}</strong>
                      <span>
                        {providerLabel(model.type)}
                        {model.api_key_set ? " · API key set" : ""}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="onboarding-exchange-tray-remove"
                      aria-label={`Remove ${model.title}`}
                      disabled={busy}
                      onClick={() => void removeModel(model)}
                    >
                      <X size={16} strokeWidth={2} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {availableProviders.length > 0 && (
            <button
              type="button"
              className="onboarding-exchange-add"
              onClick={openPicker}
              disabled={busy || loading}
              aria-label="Add provider"
            >
              <Plus size={22} strokeWidth={2.25} />
              <span>Add provider</span>
            </button>
          )}
        </div>
      </div>

      <div className="onboarding-welcome-actions">
        <button
          type="button"
          className="btn btn-secondary onboarding-welcome-cta"
          onClick={onBack}
          disabled={busy || loading}
        >
          Back
        </button>
        <button
          type="button"
          className="btn onboarding-welcome-cta"
          onClick={handlePrimary}
          disabled={busy || loading}
        >
          {hasModel ? "Continue" : "Skip for now"}
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
            aria-labelledby="onboarding-model-picker-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="onboarding-welcome-copy">
              <h1 id="onboarding-model-picker-title">Add a provider</h1>
              <p>Choose an API source. One connection per provider.</p>
            </div>

            <div className="onboarding-exchange-groups">
              <section className="onboarding-exchange-group">
                <h3 className="onboarding-exchange-group-title">Providers</h3>
                <div className="onboarding-exchange-grid">
                  {availableProviders.map((item: ModelProvider) => (
                    <button
                      key={item.type}
                      type="button"
                      className="onboarding-exchange-card"
                      disabled={busy}
                      onClick={() => selectProvider(item.type)}
                    >
                      <img
                        src={item.logo}
                        alt=""
                        width={36}
                        height={36}
                        className="onboarding-model-logo"
                      />
                      <div className="onboarding-exchange-card-text">
                        <strong>{item.label}</strong>
                        <span>{item.description}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </section>
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

      {connecting && provider && selectedType && (
        <div
          className="onboarding-nested-overlay"
          role="presentation"
          onClick={closeConnect}
        >
          <div
            className="onboarding-nested-dialog onboarding-nested-dialog--wide"
            role="dialog"
            aria-modal="true"
            aria-labelledby="onboarding-model-connect-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="onboarding-model-connect-header">
              <img
                src={provider.logo}
                alt=""
                width={48}
                height={48}
                className="onboarding-model-logo"
              />
              <div className="onboarding-welcome-copy">
                <h1 id="onboarding-model-connect-title">Connect {provider.label}</h1>
                <p>
                  {provider.apiKeyOnly
                    ? "Enter your API key, then test to save."
                    : "Enter connection details, then test to save."}
                </p>
              </div>
            </div>

            <div className="settings-form model-overlay-form onboarding-model-form">
              {provider.showBaseUrl && (
                <label>
                  Base URL
                  <input
                    value={form.base_url}
                    onChange={(event) => setForm({ ...form, base_url: event.target.value })}
                    placeholder={provider.defaults.base_url}
                    disabled={saving || testing}
                  />
                </label>
              )}
              <label>
                API key {provider.apiKeyRequired ? "" : "(optional)"}
                <input
                  type="password"
                  value={form.api_key}
                  onChange={(event) => setForm({ ...form, api_key: event.target.value })}
                  disabled={saving || testing}
                />
              </label>
            </div>

            {message && <p className="settings-message">{message}</p>}
            {error && <p className="settings-error">{error}</p>}

            <div className="onboarding-welcome-actions">
              <button
                type="button"
                className="btn btn-secondary onboarding-welcome-cta"
                onClick={closeConnect}
                disabled={saving || testing}
              >
                Cancel
              </button>
              {provider.supportsConnectionTest ? (
                <button
                  type="button"
                  className="btn onboarding-welcome-cta"
                  onClick={() => void handleTestAndSave()}
                  disabled={!canSubmit || saving || testing}
                >
                  {testing || saving ? "Connecting…" : "Test & save"}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn onboarding-welcome-cta"
                  onClick={() => void handleSaveWithoutTest()}
                  disabled={!canSubmit || saving}
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
