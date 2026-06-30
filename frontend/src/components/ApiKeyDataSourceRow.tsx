import { useRef, useState } from "react";
import type { MassiveConnection, NewsApiConnection } from "../api/client";
import DataSourceLogo from "./DataSourceLogo";
import ToggleSwitch from "./ToggleSwitch";
import type { DataSource } from "../lib/dataSources";

export type ApiKeyConnection = NewsApiConnection | MassiveConnection;

type ApiKeyDataSourceRowProps = {
  source: DataSource;
  connection: ApiKeyConnection;
  enableLabel: string;
  apiKeyPlaceholder: string;
  onConnectionChange: (connection: ApiKeyConnection) => void;
  onDisconnected?: () => void;
  testConnection: (data?: { api_key?: string }) => Promise<{ ok: boolean; message: string }>;
  saveConnection: (data: { api_key: string; enabled: boolean }) => Promise<ApiKeyConnection>;
  deleteConnection: () => Promise<ApiKeyConnection>;
};

export default function ApiKeyDataSourceRow({
  source,
  connection,
  enableLabel,
  apiKeyPlaceholder,
  onConnectionChange,
  onDisconnected,
  testConnection,
  saveConnection,
  deleteConnection,
}: ApiKeyDataSourceRowProps) {
  const [apiKey, setApiKey] = useState("");
  const [apiKeySet, setApiKeySet] = useState(connection.api_key_set);
  const [enabled, setEnabled] = useState(connection.enabled);
  const [testing, setTesting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const enabledRef = useRef(enabled);
  const apiKeyRef = useRef(apiKey);
  enabledRef.current = enabled;
  apiKeyRef.current = apiKey;

  const keyDirty = apiKey.trim().length > 0;
  const canEnable = apiKeySet && !keyDirty;
  const busy = testing || deleting;

  async function handleEnabledChange(next: boolean) {
    if (!canEnable) return;

    const previous = enabled;
    enabledRef.current = next;
    setEnabled(next);
    setError(null);

    try {
      const data = await saveConnection({
        api_key: apiKeyRef.current,
        enabled: next,
      });
      setEnabled(data.enabled);
      setApiKeySet(data.api_key_set);
      setApiKey("");
      onConnectionChange(data);
    } catch (err) {
      enabledRef.current = previous;
      setEnabled(previous);
      setError(err instanceof Error ? err.message : "Failed to save");
    }
  }

  async function handleTest() {
    setTesting(true);
    setMessage(null);
    setError(null);
    try {
      const result = await testConnection(
        apiKey.trim() ? { api_key: apiKey } : undefined,
      );
      if (!result.ok) {
        setError(result.message);
        return;
      }

      const isNewConnection = !apiKeySet && Boolean(apiKey.trim());
      const nextEnabled = isNewConnection ? true : enabled;
      enabledRef.current = nextEnabled;
      setEnabled(nextEnabled);

      const data = await saveConnection({ api_key: apiKey, enabled: nextEnabled });
      setEnabled(data.enabled);
      setApiKeySet(data.api_key_set);
      setApiKey("");
      setMessage(result.message);
      onConnectionChange(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  }

  async function handleDisconnect() {
    setDeleting(true);
    setMessage(null);
    setError(null);
    try {
      const data = await deleteConnection();
      setEnabled(data.enabled);
      setApiKeySet(data.api_key_set);
      setApiKey("");
      onConnectionChange(data);
      onDisconnected?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disconnect");
      setDeleting(false);
    }
  }

  return (
    <li className="model-list-item data-source-list-item">
      <div className="data-source-list-body">
        <div className="data-source-list-header">
          <div className="data-source-list-title">
            <DataSourceLogo source={source} size={40} />
            <div className="model-list-main">
              <strong>{source.name}</strong>
              <span className="settings-muted">
                {source.category} · {source.description}
              </span>
              {!canEnable && (
                <span className="settings-muted">
                  Test connection to verify and save your API key.
                </span>
              )}
            </div>
          </div>
          <ToggleSwitch
            label={enableLabel}
            checked={enabled}
            disabled={!canEnable || busy}
            onChange={handleEnabledChange}
          />
        </div>
        <div className="data-source-list-form settings-form">
          <label>
            API key
            <input
              type="password"
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setMessage(null);
                setError(null);
              }}
              placeholder={apiKeySet ? "Key saved — enter to replace" : apiKeyPlaceholder}
              disabled={busy}
            />
          </label>
          <div className="settings-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleTest}
              disabled={busy || (!apiKey.trim() && !apiKeySet)}
            >
              {testing
                ? "Testing…"
                : keyDirty || !apiKeySet
                  ? "Test & save connection"
                  : "Test connection"}
            </button>
            {apiKeySet && (
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={handleDisconnect}
                disabled={busy}
              >
                {deleting ? "Disconnecting…" : "Disconnect"}
              </button>
            )}
          </div>
          {message && <p className="settings-message">{message}</p>}
          {error && <p className="settings-error">{error}</p>}
        </div>
      </div>
    </li>
  );
}
