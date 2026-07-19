import { useCallback, useEffect, useState } from "react";
import {
  api,
  type OandaAccount,
  type OandaConnection,
  type OandaEnvironment,
} from "../../api/client";

type OandaConnectionFormProps = {
  connection: OandaConnection;
  onSaved: (connection: OandaConnection) => void;
  disabled?: boolean;
};

export default function OandaConnectionForm({
  connection,
  onSaved,
  disabled = false,
}: OandaConnectionFormProps) {
  const [environment, setEnvironment] = useState<OandaEnvironment>(connection.environment);
  const [accessToken, setAccessToken] = useState("");
  const [accountId, setAccountId] = useState(connection.account_id ?? "");
  const [accounts, setAccounts] = useState<OandaAccount[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const busy = disabled || testing || saving || loadingAccounts;
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
      if (result.suggested_environment) {
        setEnvironment(result.suggested_environment);
      }
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
        if (result.suggested_environment) {
          setMessage(result.message);
        }
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
  }, [accessToken, connection.access_token_set, environment]);

  useEffect(() => {
    if (!connection.access_token_set) return;
    void loadAccounts();
  }, [connection.access_token_set, environment, loadAccounts]);

  async function handleTest() {
    setTesting(true);
    setMessage(null);
    setError(null);
    try {
      const result = await api.testOandaConnection({
        access_token: accessToken,
        environment,
      });
      if (result.suggested_environment) {
        setEnvironment(result.suggested_environment);
      }
      if (result.ok) {
        setAccounts(result.accounts);
        if (!accountId && result.accounts.length > 0) {
          setAccountId(result.accounts[0].id);
        }
        setMessage(result.message);
      } else {
        const length = result.diagnostics?.token_length;
        setError(
          length != null ? `${result.message} (received ${length} characters)` : result.message,
        );
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
      setMessage("Connected");
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="onboarding-exchange-form">
      <p className="onboarding-step-lead">
        Connect OANDA with a personal access token (practice recommended). In OANDA Hub, open
        Tools → API → Generate, copy the full key, and match Environment to that login
        (Practice vs Live).
      </p>
      <div className="settings-form">
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
              disabled={busy}
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
            disabled={busy}
          />
        </label>
        <label>
          Account
          <div className="settings-select-wrap">
            <select
              className="settings-select"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              disabled={busy || accounts.length === 0}
            >
              {loadingAccounts ? (
                <option value="">Loading accounts…</option>
              ) : accounts.length === 0 ? (
                <option value="">
                  {canLoadAccounts ? "No accounts found" : "Test connection to load accounts"}
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
        </label>
      </div>
      {message && <p className="settings-message">{message}</p>}
      {error && <p className="settings-error">{error}</p>}
      <div className="onboarding-step-actions">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleTest}
          disabled={busy || (!connection.access_token_set && !accessToken.trim())}
        >
          {testing ? "Testing…" : "Test connection"}
        </button>
        <button type="button" className="btn" onClick={handleSave} disabled={busy || !canSave}>
          {saving ? "Saving…" : connection.connected ? "Update connection" : "Save & continue"}
        </button>
      </div>
    </div>
  );
}
