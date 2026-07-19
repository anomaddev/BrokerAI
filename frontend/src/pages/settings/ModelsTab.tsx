import { useEffect, useMemo, useRef, useState } from "react";
import { api, type AiModel, type ModelProviderType } from "../../api/client";
import ToggleSwitch from "../../components/ToggleSwitch";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import useAutoSave from "../../hooks/useAutoSave";
import { getProvider, MODEL_PROVIDERS, providerLabel } from "./modelProviders";

type OverlayStep = "type" | "form" | "edit" | null;

const EMPTY_FORM = {
  base_url: "",
  api_key: "",
};

function Overlay({
  children,
  onClose,
  wide,
}: {
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <div className="confirm-overlay" role="presentation" onClick={onClose}>
      <div
        className={`model-overlay-dialog${wide ? " model-overlay-dialog--wide" : ""}`}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

export default function ModelsTab() {
  const [models, setModels] = useState<AiModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overlay, setOverlay] = useState<OverlayStep>(null);
  const [selectedType, setSelectedType] = useState<ModelProviderType>("open_webui");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AiModel | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const formRef = useRef(form);
  const editingIdRef = useRef(editingId);
  formRef.current = form;
  editingIdRef.current = editingId;

  const connectedTypes = useMemo(
    () => new Set(models.map((model) => model.type)),
    [models],
  );
  const availableProviders = useMemo(
    () => MODEL_PROVIDERS.filter((item) => !connectedTypes.has(item.type)),
    [connectedTypes],
  );

  async function loadModels() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listModels();
      setModels(data.models);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load models");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadModels();
  }, []);

  function resetOverlay() {
    setOverlay(null);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setMessage(null);
  }

  function closeOverlay() {
    if (saving || testing || deleting) return;
    resetOverlay();
  }

  function startAdd() {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setSelectedType(availableProviders[0]?.type ?? "open_webui");
    setMessage(null);
    setOverlay("type");
  }

  function selectProvider(type: ModelProviderType) {
    const provider = getProvider(type);
    if (!provider) return;
    setSelectedType(type);
    setForm({
      base_url: provider.defaults.base_url,
      api_key: "",
    });
    setOverlay("form");
  }

  function startEdit(model: AiModel) {
    setForm({
      base_url: model.base_url,
      api_key: "",
    });
    setSelectedType((model.type as ModelProviderType) || "open_webui");
    setEditingId(model.id);
    setOverlay("edit");
    setMessage(null);
  }

  function canToggleModel(model: AiModel): boolean {
    const provider = getProvider(model.type);
    if (provider?.apiKeyRequired && !model.api_key_set) return false;
    return true;
  }

  async function handleToggle(model: AiModel, enabled: boolean) {
    if (!canToggleModel(model)) return;
    try {
      const updated = await api.toggleModel(model.id, enabled);
      setModels((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update model");
    }
  }

  async function persistEditWithoutKeyChange() {
    const id = editingIdRef.current;
    if (!id) return;
    const snapshot = formRef.current;
    const updated = await api.updateModel(id, {
      base_url: snapshot.base_url,
    });
    setModels((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
  }

  const { scheduleSave, markReady, markNotReady } = useAutoSave({
    onSave: persistEditWithoutKeyChange,
    canSave: () =>
      overlay === "edit" &&
      Boolean(editingIdRef.current) &&
      Boolean(getProvider(selectedType)?.showBaseUrl) &&
      !formRef.current.api_key.trim(),
  });

  useEffect(() => {
    if (
      overlay === "edit" &&
      editingId &&
      getProvider(selectedType)?.showBaseUrl &&
      !form.api_key.trim()
    ) {
      markReady();
      scheduleSave(300);
    } else {
      markNotReady();
    }
  }, [
    overlay,
    editingId,
    selectedType,
    form.base_url,
    form.api_key,
    markReady,
    markNotReady,
    scheduleSave,
  ]);

  async function saveAfterSuccessfulTest() {
    const snapshot = formRef.current;
    if (overlay === "edit" && editingId) {
      const updated = await api.updateModel(editingId, {
        base_url: snapshot.base_url,
        api_key: snapshot.api_key || undefined,
      });
      setModels((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      resetOverlay();
      return;
    }

    const created = await api.createModel({
      title: getProvider(selectedType)?.defaults.title || providerLabel(selectedType),
      type: selectedType,
      base_url: snapshot.base_url,
      api_key: snapshot.api_key,
      enabled: true,
    });
    setModels((prev) => [...prev, created]);
    resetOverlay();
  }

  async function handleTest(modelId?: string) {
    setTesting(true);
    setMessage(null);
    setError(null);
    try {
      let result;
      if (modelId) {
        result = await api.testModel(modelId);
      } else if (editingId && !form.api_key.trim()) {
        result = await api.testModel(editingId);
      } else if (getProvider(selectedType)?.supportsConnectionTest) {
        result = await api.testModelConnection({
          title: getProvider(selectedType)?.defaults.title || providerLabel(selectedType),
          type: selectedType,
          base_url: form.base_url,
          api_key: form.api_key,
        });
      } else {
        setMessage("Connection testing for this provider is not available yet.");
        return;
      }

      if (!result.ok) {
        setMessage(result.message);
        return;
      }

      setMessage(result.message);

      const shouldSaveAfterTest =
        result.ok &&
        provider?.supportsConnectionTest &&
        (overlay === "form" || (overlay === "edit" && keyDirty));

      if (shouldSaveAfterTest) {
        setSaving(true);
        try {
          await saveAfterSuccessfulTest();
        } finally {
          setSaving(false);
        }
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await saveAfterSuccessfulTest();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save model");
    } finally {
      setSaving(false);
    }
  }

  async function handleConfirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setError(null);
    setMessage(null);
    try {
      await api.deleteModel(deleteTarget.id);
      setModels((prev) => prev.filter((m) => m.id !== deleteTarget.id));
      if (editingId === deleteTarget.id) {
        resetOverlay();
      }
      setDeleteTarget(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete model");
    } finally {
      setDeleting(false);
    }
  }

  const provider = getProvider(selectedType);
  const formTitle =
    overlay === "edit"
      ? `Edit ${providerLabel(selectedType)}`
      : provider
        ? `Connect ${provider.label}`
        : "Connect provider";
  const formSubtitle =
    overlay === "edit"
      ? provider?.apiKeyOnly
        ? "Update your API key, then test to save."
        : "Update connection details, then test to save."
      : provider?.apiKeyOnly
        ? "Enter your API key, then test to save."
        : "Enter connection details, then test to save.";

  const keyDirty = Boolean(form.api_key.trim());
  const showSaveButton = Boolean(provider && !provider.supportsConnectionTest && (overlay === "form" || keyDirty));

  const canTest =
    (provider?.apiKeyOnly || Boolean(form.base_url.trim())) &&
    (!provider?.apiKeyRequired || overlay === "edit" || Boolean(form.api_key.trim()));

  const canSaveWithoutTest =
    showSaveButton &&
    (provider?.apiKeyOnly || Boolean(form.base_url.trim())) &&
    (!provider?.apiKeyRequired || overlay === "edit" || Boolean(form.api_key.trim()));

  const testButtonLabel =
    overlay === "form" || keyDirty
      ? testing
        ? "Testing…"
        : "Test & save connection"
      : testing
        ? "Testing…"
        : "Test connection";

  return (
    <>
      <div className="settings-panel">
        <SettingsPanelHeader
          title="Models"
          description="API sources for research. Pick specific models under Reports."
          error={!overlay ? error : null}
          message={!overlay ? message : null}
          action={
            availableProviders.length > 0 ? (
              <button type="button" className="btn" onClick={startAdd}>
                Add provider
              </button>
            ) : null
          }
        />
        <div className="settings-panel-body">
        {loading && <p className="settings-muted">Loading providers…</p>}
        {!loading && models.length === 0 && (
          <p className="settings-muted">No API sources configured yet.</p>
        )}
        <ul className="model-list">
          {models.map((model) => {
            const modelProvider = getProvider(model.type);
            return (
            <li key={model.id} className="model-list-item">
              {modelProvider ? (
                <img
                  src={modelProvider.logo}
                  alt=""
                  className="model-list-logo"
                  width={40}
                  height={40}
                />
              ) : null}
              <div className="model-list-main">
                <strong>{model.title}</strong>
                <span className="settings-muted">
                  {providerLabel(model.type)}
                  {model.api_key_set ? " · API key set" : " · API key missing"}
                </span>
              </div>
              <div className="model-list-actions">
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => startEdit(model)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleTest(model.id)}
                  disabled={testing || deleting}
                >
                  Test
                </button>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  onClick={() => setDeleteTarget(model)}
                  disabled={testing || deleting || saving}
                >
                  Delete
                </button>
                <ToggleSwitch
                  label={`Enable ${model.title}`}
                  checked={model.enabled}
                  disabled={!canToggleModel(model)}
                  onChange={(enabled) => handleToggle(model, enabled)}
                />
              </div>
            </li>
            );
          })}
        </ul>
        </div>
      </div>

      {overlay === "type" && (
        <Overlay onClose={closeOverlay}>
          <h4 className="model-overlay-title">Add provider</h4>
          <p className="model-overlay-desc">Choose an API source to connect. One connection per provider.</p>
          <div className="model-provider-grid">
            {availableProviders.map((item) => (
              <button
                key={item.type}
                type="button"
                className="model-provider-card"
                onClick={() => selectProvider(item.type)}
              >
                <img src={item.logo} alt="" className="model-provider-logo" width={40} height={40} />
                <span className="model-provider-card-label">{item.label}</span>
                <span className="model-provider-card-desc">{item.description}</span>
              </button>
            ))}
          </div>
          <div className="confirm-actions">
            <button type="button" className="btn btn-secondary" onClick={closeOverlay}>
              Cancel
            </button>
          </div>
        </Overlay>
      )}

      {(overlay === "form" || overlay === "edit") && provider && (
        <Overlay onClose={closeOverlay} wide>
          <div className="model-form-header">
            <img src={provider.logo} alt="" className="model-provider-logo" width={48} height={48} />
            <div className="model-form-header-copy">
              <h4 className="model-overlay-title">{formTitle}</h4>
              <p className="model-overlay-desc">{formSubtitle}</p>
              {overlay === "form" && (
                <button
                  type="button"
                  className="model-form-back"
                  onClick={() => {
                    setMessage(null);
                    setError(null);
                    setOverlay("type");
                  }}
                >
                  Change provider
                </button>
              )}
            </div>
          </div>
          <div className="settings-form model-overlay-form">
            {provider.showBaseUrl && (
              <label>
                Base URL
                <input
                  value={form.base_url}
                  onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                  placeholder={provider.defaults.base_url}
                />
              </label>
            )}
            <label>
              API key {provider.apiKeyRequired ? "" : "(optional)"}
              <input
                type="password"
                value={form.api_key}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                placeholder={overlay === "edit" ? "Leave blank to keep current key" : ""}
              />
            </label>
          </div>
          {message && <p className="settings-message">{message}</p>}
          {error && <p className="settings-error">{error}</p>}
          <div className="confirm-actions">
            <button type="button" className="btn btn-secondary" onClick={closeOverlay} disabled={saving}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => handleTest()}
              disabled={testing || !canTest}
            >
              {testButtonLabel}
            </button>
            {showSaveButton && (
              <button
                type="button"
                className="btn"
                onClick={handleSave}
                disabled={saving || !canSaveWithoutTest}
              >
                {saving ? "Saving…" : "Save"}
              </button>
            )}
          </div>
        </Overlay>
      )}

      {deleteTarget && (
        <div className="confirm-overlay" role="presentation" onClick={() => !deleting && setDeleteTarget(null)}>
          <div
            className="confirm-dialog"
            role="alertdialog"
            aria-labelledby="delete-model-title"
            aria-describedby="delete-model-message"
            onClick={(e) => e.stopPropagation()}
          >
            <h4 id="delete-model-title">Delete &ldquo;{deleteTarget.title}&rdquo;?</h4>
            <p id="delete-model-message">
              This API source will be permanently removed. Research settings that use it will need
              to be updated under Settings → Reports.
            </p>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={deleting}
                onClick={() => setDeleteTarget(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={deleting}
                onClick={handleConfirmDelete}
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
