import { useCallback, useEffect, useState } from "react";
import {
  api,
  type OandaAccount,
  type OandaConnection,
  type OandaEnvironment,
} from "../api/client";
import ExchangeLogo from "./ExchangeLogo";
import { getExchange } from "../lib/exchanges";

type OandaConnectionOverlayProps = {
  connection: OandaConnection;
  onClose: () => void;
  onSaved: (connection: OandaConnection) => void;
};

export default function OandaConnectionOverlay({
  connection,
  onClose,
  onSaved,
}: OandaConnectionOverlayProps) {
  const [environment, setEnvironment] = useState<OandaEnvironment>(connection.environment);
  const [accessToken, setAccessToken] = useState("");
  const [accountId, setAccountId] = useState(connection.account_id ?? "");
  const [accounts, setAccounts] = useState<OandaAccount[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const busy = testing || saving || deleting || loadingAccounts;
  const canSave =
    Boolean(accountId) && (connection.access_token_set || Boolean(accessToken.trim()));
  const canLoadAccounts = connection.access_token_set || Boolean(accessToken.trim());

  const loadAccounts = useCallback(async () => {
    if (!connection.access_token_set && !accessToken.trim()) {
      setAccounts([]);
      return;
    }

    setLoadingAccounts(true);
    setError(null);
    try {
      const result = await api.testOandaConnection({
        access_token: accessToken,
        environment,
      });
      if (result.ok) {
        setAccounts(result.accounts);
        setAccountId((current) => {
          if (
            current &&
            result.accounts.length > 0 &&
            !result.accounts.some((account) => account.id === current)
          ) {
            return result.accounts[0].id;
          }
          return current;
        });
      } else {
        setAccounts([]);
        setError(result.message);
      }
    } catch (err) {
      setAccounts([]);
      setError(err instanceof Error ? err.message : "Failed to load accounts");
    } finally {
      setLoadingAccounts(false);
    }
  }, [connection.access_token_set, environment]);

  useEffect(() => {
    if (!connection.access_token_set) return;
    void loadAccounts();
  }, [connection.access_token_set, environment, loadAccounts]);

  function close() {
    if (busy) return;
    onClose();
  }

  async function handleTest() {
    setTesting(true);
    setMessage(null);
    setError(null);
    try {
      const result = await api.testOandaConnection({
        access_token: accessToken,
        environment,
      });
      if (result.ok) {
        setAccounts(result.accounts);
        if (!accountId && result.accounts.length > 0) {
          setAccountId(result.accounts[0].id);
        }
        setMessage(result.message);
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const saved = await api.saveOandaConnection({
        access_token: accessToken,
        environment,
        account_id: accountId,
      });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
      setSaving(false);
    }
  }

  async function handleDisconnect() {
    setDeleting(true);
    setMessage(null);
    setError(null);
    try {
      await api.deleteOandaConnection();
      onSaved({
        exchange_id: "oanda",
        connected: false,
        environment: "practice",
        account_id: null,
        access_token: null,
        access_token_set: false,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disconnect");
      setDeleting(false);
    }
  }

  const oanda = getExchange("oanda");

  return (
    <div className="confirm-overlay" role="presentation" onClick={close}>
      <div
        className="model-overlay-dialog model-overlay-dialog--wide exchange-connect-dialog"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="model-form-header">
          {oanda && <ExchangeLogo exchange={oanda} size={36} className="exchange-logo model-provider-logo" />}
          <div>
            <h4 className="model-overlay-title">
              {connection.connected ? "Manage OANDA" : "Connect OANDA"}
            </h4>
          </div>
        </div>
        <p className="model-overlay-desc">
          Forex and CFD trading via the OANDA REST-v20 API. Generate a personal access token from
          your OANDA account under My Services → Manage API Access.
        </p>
        <div className="settings-form model-overlay-form">
          <label>
            Environment
            <div className="settings-select-wrap">
              <select
                className="settings-select"
                value={environment}
                onChange={(e) => {
                  setEnvironment(e.target.value as OandaEnvironment);
                  setMessage(null);
                  setError(null);
                }}
                disabled={loadingAccounts}
              >
                <option value="practice">Practice (fxPractice)</option>
                <option value="live">Live (fxTrade)</option>
              </select>
            </div>
          </label>
          <label>
            Personal access token
            <input
              type="password"
              value={accessToken}
              onChange={(e) => setAccessToken(e.target.value)}
              placeholder={
                connection.access_token_set ? "Token saved — enter to replace" : "Enter OANDA token"
              }
            />
          </label>
          <label>
            Account
            <div className="settings-select-wrap">
              <select
                className="settings-select"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                disabled={loadingAccounts || accounts.length === 0}
              >
                {loadingAccounts ? (
                  <option value="">Loading accounts…</option>
                ) : accounts.length === 0 ? (
                  <option value="">
                    {canLoadAccounts
                      ? "No accounts found"
                      : "Test connection to load accounts"}
                  </option>
                ) : (
                  <>
                    <option value="">Select an account</option>
                    {accounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.id}
                      </option>
                    ))}
                  </>
                )}
              </select>
            </div>
            {!loadingAccounts && accounts.length === 0 && !canLoadAccounts && (
              <span className="settings-field-hint">
                Run a connection test after entering your token to load available accounts.
              </span>
            )}
          </label>
        </div>
        {message && <p className="settings-message model-overlay-feedback">{message}</p>}
        {error && <p className="settings-error model-overlay-feedback">{error}</p>}
        <div className="confirm-actions model-overlay-actions">
          <button type="button" className="btn btn-secondary" onClick={close} disabled={busy}>
            Cancel
          </button>
          {connection.connected && (
            <button
              type="button"
              className="btn btn-danger"
              onClick={handleDisconnect}
              disabled={busy}
            >
              {deleting ? "Disconnecting…" : "Disconnect"}
            </button>
          )}
          <div className="model-overlay-actions-primary">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleTest}
              disabled={busy || (!connection.access_token_set && !accessToken.trim())}
            >
              {testing ? "Testing…" : "Test connection"}
            </button>
            <button
              type="button"
              className="btn"
              onClick={handleSave}
              disabled={busy || !canSave}
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
