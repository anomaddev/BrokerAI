import { useEffect, useRef, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import {
  api,
  type UpdateSettingsConfig,
  type UpdateStatusResponse,
} from "../api/client";

const TABS = [
  { path: "general", label: "General" },
  { path: "ai-models", label: "AI Models" },
  { path: "data-connections", label: "Data Connections" },
  { path: "brokers", label: "Brokers" },
  { path: "system", label: "System" },
];

const SUB_BROKERS = ["Crypto", "Forex", "Stocks", "Futures", "Options"];

function formatVersionLine(info?: { track?: string; ref?: string; commit_short?: string }): string {
  if (!info?.commit_short && !info?.ref) return "—";
  const pin = info.track && info.ref ? `${info.track}:${info.ref}` : info.ref ?? "—";
  const commit = info.commit_short ?? "—";
  return `${pin} @ ${commit}`;
}

function hasVersionInfo(info?: {
  track?: string;
  ref?: string;
  commit_short?: string;
  commit?: string;
}): boolean {
  if (!info) return false;
  const commit = (info.commit_short ?? info.commit ?? "").trim();
  if (commit && commit !== "—" && commit !== "unknown" && commit.length >= 4) {
    return true;
  }
  const ref = (info.ref ?? "").trim();
  return Boolean(ref && ref !== "—" && ref !== "unknown" && ref !== "unset");
}

type UpdateTrack = UpdateSettingsConfig["update_track"];

const UPDATE_TRACK_OPTIONS: Array<{ value: UpdateTrack; label: string }> = [
  { value: "branch", label: "Branch — latest commit" },
  { value: "release", label: "Release — pinned version" },
  { value: "latest-release", label: "Latest release" },
];

function computeConfiguredPin(
  config: Pick<UpdateSettingsConfig, "update_track" | "branch" | "release">,
): string {
  if (config.update_track === "branch") return `branch:${config.branch || "main"}`;
  if (config.update_track === "release") {
    const tag = config.release || "unset";
    return `release:${tag.replace(/^v/, "")}`;
  }
  return "latest-release";
}

function configuredTargetInfo(
  config: Pick<UpdateSettingsConfig, "update_track" | "branch" | "release">,
) {
  if (config.update_track === "branch") {
    return { track: "branch", ref: config.branch || "main" };
  }
  if (config.update_track === "release") {
    return { track: "release", ref: (config.release || "unset").replace(/^v/, "") };
  }
  return { track: "latest-release", ref: "latest" };
}

function checkMatchesConfig(
  data: UpdateStatusResponse | null,
  config: UpdateSettingsConfig | null,
): boolean {
  if (!data || !config) return false;
  return data.configured_pin === computeConfiguredPin(config);
}

function isTrackConfigPatch(patch: Partial<UpdateSettingsConfig>): boolean {
  return (
    patch.update_track !== undefined ||
    patch.branch !== undefined ||
    patch.release !== undefined
  );
}

function GeneralTab() {
  return (
    <div className="placeholder">
      General settings will be configured here (bot name, timezone, etc.).
    </div>
  );
}

function AiModelsTab() {
  return (
    <div className="placeholder">
      Researcher AI models will be configured here in a future release.
    </div>
  );
}

function DataConnectionsTab() {
  return (
    <div className="placeholder">
      Data Manager API connections will be configured here in a future release.
    </div>
  );
}

function BrokersTab() {
  return (
    <div className="card-grid">
      {SUB_BROKERS.map((name) => (
        <div key={name} className="card">
          <h3>{name}</h3>
          <span className="badge stopped">stub</span>
        </div>
      ))}
    </div>
  );
}

function resolveCheckError(data: UpdateStatusResponse | null): string | null {
  if (!data) return null;
  if (data.check_error) return data.check_error;

  if (data.checked && data.update_available == null) {
    const msg = data.message?.trim();
    if (!msg) return null;
    const benign = new Set([
      "Local dev — checking uses git; applying updates is simulated only",
      "Up to date",
      "Update available",
    ]);
    if (!benign.has(msg)) return msg;
  }

  return null;
}

function isNoReleasesError(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    lower.includes("no github releases") ||
    lower.includes("no releases or tags") ||
    lower.includes("could not resolve latest github release")
  );
}

function checkErrorTitle(message: string): string {
  return isNoReleasesError(message) ? "No releases yet" : "Update check failed";
}

type ErrorOverlayState = { title: string; message: string };

function UpdateErrorOverlay({
  title,
  message,
  onDismiss,
}: {
  title: string;
  message: string;
  onDismiss: () => void;
}) {
  return (
    <div className="confirm-overlay" role="presentation" onClick={onDismiss}>
      <div
        className="confirm-dialog confirm-dialog--error"
        role="alertdialog"
        aria-labelledby="update-error-title"
        aria-describedby="update-error-message"
        onClick={(e) => e.stopPropagation()}
      >
        <h4 id="update-error-title">{title}</h4>
        <p id="update-error-message">{message}</p>
        <div className="confirm-actions">
          <button className="btn" type="button" onClick={onDismiss}>
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

function UpdatesCard() {
  const [config, setConfig] = useState<UpdateSettingsConfig | null>(null);
  const [update, setUpdate] = useState<UpdateStatusResponse | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [errorOverlay, setErrorOverlay] = useState<ErrorOverlayState | null>(null);
  const skipSaveRef = useRef(true);
  const saveTimerRef = useRef<number | null>(null);
  const saveInFlightRef = useRef(false);
  const pendingSaveRef = useRef<UpdateSettingsConfig | null>(null);
  const configRef = useRef<UpdateSettingsConfig | null>(null);
  const userEditedRef = useRef(false);
  const checkInFlightRef = useRef(false);

  function mergeSavedMetadata(
    current: UpdateSettingsConfig,
    saved: UpdateSettingsConfig,
  ): UpdateSettingsConfig {
    return {
      ...current,
      configured_pin: saved.configured_pin,
      config_path: saved.config_path,
      config_writable: saved.config_writable,
      repo: saved.repo,
    };
  }

  function showErrorOverlay(title: string, message: string) {
    setErrorOverlay({ title, message });
  }

  function applyUpdateData(data: UpdateStatusResponse) {
    setUpdate(data);
    const checkErr = resolveCheckError(data);
    setCheckError(checkErr);
    if (checkErr) {
      showErrorOverlay(checkErrorTitle(checkErr), checkErr);
      return;
    }
    if (data.error?.trim()) {
      showErrorOverlay("Update failed", data.error.trim());
    }
  }

  function invalidateVersionMeta() {
    setCheckError(null);
    setUpdate((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        configured_pin: configRef.current ? computeConfiguredPin(configRef.current) : prev.configured_pin,
        update_track: configRef.current?.update_track ?? prev.update_track,
        branch: configRef.current?.branch ?? prev.branch,
        release: configRef.current?.release ?? prev.release,
        check: null,
        update_available: null,
        checked: false,
      };
    });
  }

  const loadStatus = () => {
    if (checkInFlightRef.current) return Promise.resolve();
    return api
      .updateStatus()
      .then((data) => {
        applyUpdateData(data);
      })
      .catch((err: Error) => showErrorOverlay("Update status unavailable", err.message));
  };

  const runCheck = async () => {
    if (checkInFlightRef.current) return;
    checkInFlightRef.current = true;
    try {
      const data = await api.checkForUpdate();
      applyUpdateData(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Update check failed";
      setCheckError(message);
      showErrorOverlay(checkErrorTitle(message), message);
    } finally {
      checkInFlightRef.current = false;
    }
  };

  useEffect(() => {
    let cancelled = false;

    async function init() {
      setLoading(true);
      try {
        const [settingsData, checkData] = await Promise.all([
          api.getUpdateSettings(),
          api.checkForUpdate(),
        ]);
        if (!cancelled) {
          setConfig((current) => {
            if (current || userEditedRef.current) return current;
            configRef.current = settingsData;
            return settingsData;
          });
          applyUpdateData(checkData);
          skipSaveRef.current = false;
        }
      } catch (err) {
        if (!cancelled) {
          showErrorOverlay(
            "Failed to load update settings",
            err instanceof Error ? err.message : "Failed to load update settings",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    init();
    return () => {
      cancelled = true;
      if (saveTimerRef.current) {
        window.clearTimeout(saveTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (update?.status !== "running") return undefined;
    const id = window.setInterval(loadStatus, 1000);
    return () => window.clearInterval(id);
  }, [update?.status]);

  useEffect(() => {
    if (update?.status === "running") {
      setUpdating(true);
      return;
    }
    if (update?.status && update.status !== "running") {
      setUpdating(false);
    }
  }, [update?.status]);

  async function drainSaveQueue() {
    if (saveInFlightRef.current) return;

    saveInFlightRef.current = true;
    setSaving(true);
    try {
      while (pendingSaveRef.current) {
        const next = pendingSaveRef.current;
        pendingSaveRef.current = null;

        if (!next.config_writable || !canPersistConfig(next)) {
          continue;
        }

        const saved = await api.saveUpdateSettings({
          update_track: next.update_track,
          branch: next.branch,
          release: next.release,
          auto_update: next.auto_update,
        });

        if (!pendingSaveRef.current) {
          setConfig((current) => {
            if (!current) {
              configRef.current = saved;
              return saved;
            }
            const merged = mergeSavedMetadata(current, saved);
            configRef.current = merged;
            return merged;
          });
        }

        setChecking(true);
        try {
          await runCheck();
        } finally {
          setChecking(false);
        }
      }
    } catch (err) {
      pendingSaveRef.current = null;
      showErrorOverlay(
        "Failed to save settings",
        err instanceof Error ? err.message : "Failed to save settings",
      );
    } finally {
      setSaving(false);
      saveInFlightRef.current = false;
      if (pendingSaveRef.current) {
        void drainSaveQueue();
      }
    }
  }

  function persistConfig(next: UpdateSettingsConfig) {
    if (!next.config_writable || !canPersistConfig(next)) return;
    configRef.current = next;
    pendingSaveRef.current = next;
    void drainSaveQueue();
  }

  function scheduleSave(debounceMs = 0) {
    const latest = configRef.current;
    if (skipSaveRef.current || !latest?.config_writable || !canPersistConfig(latest)) return;

    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
    }

    const delay = debounceMs > 0 ? debounceMs : 150;
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      const toSave = configRef.current;
      if (toSave) void persistConfig(toSave);
    }, delay);
  }

  function applyConfig(patch: Partial<UpdateSettingsConfig>, debounceMs = 0) {
    userEditedRef.current = true;
    const trackChanged = isTrackConfigPatch(patch);
    setConfig((current) => {
      if (!current) return current;
      const next = { ...current, ...patch };
      configRef.current = next;
      scheduleSave(debounceMs);
      return next;
    });
    if (trackChanged) {
      invalidateVersionMeta();
    }
  }

  function canPersistConfig(next: UpdateSettingsConfig): boolean {
    if (next.update_track === "branch" && !next.branch.trim()) return false;
    if (next.update_track === "release" && !next.release.trim()) return false;
    return true;
  }

  async function handleCheckNow() {
    setChecking(true);
    try {
      await runCheck();
    } finally {
      setChecking(false);
    }
  }

  async function handleUpdate() {
    setUpdating(true);
    try {
      await api.triggerUpdate();
      await loadStatus();
    } catch (err) {
      setUpdating(false);
      showErrorOverlay(
        "Update failed",
        err instanceof Error ? err.message : "Update failed",
      );
    }
  }

  const status = update?.status ?? "idle";
  const progress = update?.progress ?? 0;
  const checkFresh = checkMatchesConfig(update, config);
  const resolvedCheckError = checkFresh ? (checkError ?? resolveCheckError(update)) : null;
  const installedInfo = checkFresh && update?.check?.installed
    ? update.check.installed
    : {
        track: update?.installed_track,
        ref: update?.installed_ref,
        commit_short: update?.installed_version,
      };
  const availableInfo = checkFresh ? update?.check?.available : undefined;
  const targetInfo = availableInfo ?? (config ? configuredTargetInfo(config) : undefined);
  const updateAvailable = checkFresh && update?.update_available === true;
  const hasChecked = checkFresh && update?.checked === true;
  const showInstalled = hasVersionInfo(installedInfo);
  const showTarget = Boolean(config && targetInfo);
  const configuredPin = config ? computeConfiguredPin(config) : "—";
  const formDisabled = loading || saving || !config?.config_writable;
  const repoDisplay = config?.repo?.replace(/^https?:\/\//, "") ?? "—";

  const displayStatus = loading || checking
    ? "checking"
    : resolvedCheckError
      ? "check_error"
      : status === "running"
        ? "running"
        : hasChecked && updateAvailable === false
          ? "up_to_date"
          : status;

  const statusLabel: Record<string, string> = {
    checking: "Checking…",
    check_error: "Check failed",
    idle: "Ready",
    running: "Updating…",
    success: "Update complete",
    failed: "Update failed",
    up_to_date: "Up to date",
  };

  const actionsDisabled = loading || checking || saving || updating || status === "running";

  return (
    <div className="card">
      <h3>Updates</h3>
      {update?.dev_mode ? (
        <p className="update-dev-note">
          Local dev — update checks use git; applying updates is simulated only.
        </p>
      ) : null}

      <div className="update-config-form">
        <div className="update-section-header">
          <p className="update-section-label">Update source</p>
          {saving ? <span className="update-saving-indicator">Saving…</span> : null}
        </div>

        {config?.repo ? (
          <div className="update-source-row">
            <span className="update-source-label">Source</span>
            <a
              href={config.repo}
              target="_blank"
              rel="noreferrer"
              className="update-repo-link"
            >
              {repoDisplay}
            </a>
          </div>
        ) : null}

        {config && !config.config_writable ? (
          <p className="update-readonly-note">
            Settings are read-only here. Edit {config.config_path} on the host to change the update
            path.
          </p>
        ) : null}

        <div className="field">
          <label htmlFor="update-track">Track</label>
          <div className="update-select-wrap">
            <select
              id="update-track"
              className="update-select"
              value={config?.update_track ?? "branch"}
              disabled={formDisabled}
              onChange={(e) =>
                applyConfig({ update_track: e.target.value as UpdateTrack })
              }
            >
              {UPDATE_TRACK_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {config?.update_track === "branch" ? (
          <div className="field">
            <label htmlFor="update-branch">Branch</label>
            <input
              id="update-branch"
              value={config.branch}
              disabled={formDisabled}
              placeholder="main"
              onChange={(e) => applyConfig({ branch: e.target.value }, 500)}
            />
          </div>
        ) : null}

        {config?.update_track === "release" ? (
          <div className="field">
            <label htmlFor="update-release">Release</label>
            <input
              id="update-release"
              value={config.release}
              disabled={formDisabled}
              placeholder="0.0.1"
              onChange={(e) => applyConfig({ release: e.target.value }, 500)}
            />
          </div>
        ) : null}

        <div className="update-toggle-row">
          <span className="update-toggle-label">Automatic updates</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              className="toggle-switch-input"
              checked={config?.auto_update ?? false}
              disabled={formDisabled}
              onChange={(e) => applyConfig({ auto_update: e.target.checked })}
            />
            <span className="toggle-switch-track" aria-hidden="true" />
          </label>
        </div>

        <p className="update-pin-preview">
          Pin: <strong>{configuredPin}</strong>
        </p>

        {resolvedCheckError ? (
          <div className="update-alert update-alert--error" role="alert">
            <strong>{checkErrorTitle(resolvedCheckError)}</strong>
            <p>{resolvedCheckError}</p>
          </div>
        ) : null}
      </div>

      {showInstalled || showTarget ? (
        <dl className="update-meta">
          {showInstalled ? (
            <div className="update-meta-row">
              <dt>Installed</dt>
              <dd>{formatVersionLine(installedInfo)}</dd>
            </div>
          ) : null}
          {showTarget ? (
            <div className="update-meta-row">
              <dt>{updateAvailable ? "Available" : "Target"}</dt>
              <dd>
                {checking && !availableInfo
                  ? `${formatVersionLine(targetInfo)} (checking…)`
                  : formatVersionLine(targetInfo)}
              </dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      <div className="update-status-row">
        <span className={`update-badge update-badge--${displayStatus}`}>
          {statusLabel[displayStatus] ?? displayStatus}
        </span>
        {update?.message && !loading && !checking && !resolvedCheckError ? (
          <span className="update-message">{update.message}</span>
        ) : null}
      </div>

      {(status === "running" || progress > 0) && (
        <div className="update-progress">
          <div className="update-progress-bar" style={{ width: `${progress}%` }} />
        </div>
      )}

      <div className="update-actions">
        <button
          className="btn btn-secondary"
          type="button"
          disabled={actionsDisabled}
          onClick={handleCheckNow}
        >
          {checking ? "Checking…" : "Check now"}
        </button>
        {updateAvailable ? (
          <button
            className="btn"
            type="button"
            disabled={actionsDisabled}
            onClick={handleUpdate}
          >
            {updating || status === "running" ? "Updating…" : "Update now"}
          </button>
        ) : null}
      </div>

      {update?.log_tail && update.log_tail.length > 0 ? (
        <pre className="update-log">{update.log_tail.join("\n")}</pre>
      ) : null}

      {errorOverlay ? (
        <UpdateErrorOverlay
          title={errorOverlay.title}
          message={errorOverlay.message}
          onDismiss={() => setErrorOverlay(null)}
        />
      ) : null}
    </div>
  );
}

type PowerAction = "reboot" | "shutdown";

function PowerConfirmDialog({
  action,
  busy,
  onCancel,
  onConfirm,
}: {
  action: PowerAction;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const isShutdown = action === "shutdown";
  const title = isShutdown ? "Shut down system?" : "Reboot system?";
  const message = isShutdown
    ? "BrokerAI will stop and the host will power off. You must start it manually from Proxmox or your host before BrokerAI is available again."
    : "BrokerAI will restart and be unavailable until the system comes back online.";

  return (
    <div className="confirm-overlay" role="presentation" onClick={onCancel}>
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-labelledby="power-confirm-title"
        aria-describedby="power-confirm-message"
        onClick={(e) => e.stopPropagation()}
      >
        <h4 id="power-confirm-title">{title}</h4>
        <p id="power-confirm-message">{message}</p>
        {isShutdown ? (
          <p className="confirm-warning">Shutdown requires a manual start.</p>
        ) : null}
        <div className="confirm-actions">
          <button className="btn btn-secondary" type="button" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
          <button
            className={`btn ${isShutdown ? "btn-danger" : ""}`}
            type="button"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "Working…" : isShutdown ? "Shut down" : "Reboot"}
          </button>
        </div>
      </div>
    </div>
  );
}

function PowerCard() {
  const [power, setPower] = useState<{ available: boolean; dev_mode?: boolean } | null>(null);
  const [pendingAction, setPendingAction] = useState<PowerAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  useEffect(() => {
    api.getPowerStatus().then(setPower).catch(() => setPower({ available: false }));
  }, []);

  async function handleConfirm() {
    if (!pendingAction) return;

    setError("");
    setStatusMessage("");
    setBusy(true);
    try {
      const result =
        pendingAction === "reboot"
          ? await api.rebootSystem()
          : await api.shutdownSystem();
      setStatusMessage(result.message);
      setPendingAction(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Power action failed");
    } finally {
      setBusy(false);
    }
  }

  const disabled = busy || power?.available === false;

  return (
    <div className="card">
      <h3>Power</h3>
      {power?.dev_mode ? (
        <p className="update-dev-note">Power control is disabled in local development.</p>
      ) : null}
      <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
        Reboot or shut down the host running BrokerAI.
      </p>

      {error ? <p className="error">{error}</p> : null}
      {statusMessage ? <p className="status-message">{statusMessage}</p> : null}

      <div className="update-actions">
        <button
          className="btn btn-secondary"
          type="button"
          disabled={disabled}
          onClick={() => setPendingAction("reboot")}
        >
          Reboot
        </button>
        <button
          className="btn btn-danger"
          type="button"
          disabled={disabled}
          onClick={() => setPendingAction("shutdown")}
        >
          Shut down
        </button>
      </div>

      {pendingAction ? (
        <PowerConfirmDialog
          action={pendingAction}
          busy={busy}
          onCancel={() => {
            if (!busy) setPendingAction(null);
          }}
          onConfirm={handleConfirm}
        />
      ) : null}
    </div>
  );
}

function SystemTab() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [db, setDb] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.dbStats().then(setDb).catch(() => setDb(null));
  }, []);

  const mongo = health?.mongodb as { status?: string } | undefined;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <div className="card">
        <h3>Health</h3>
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          Version: {String(health?.version ?? "—")} · Orchestrator:{" "}
          {health?.orchestrator_running ? "running" : "offline"} · MongoDB:{" "}
          {mongo?.status ?? "unknown"}
        </p>
      </div>
      <div className="card">
        <h3>MongoDB</h3>
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          Database: {String(db?.database ?? "—")}
        </p>
        {db?.collections && (
          <ul style={{ marginTop: "0.5rem", paddingLeft: "1.25rem", color: "var(--muted)" }}>
            {Object.entries(db.collections as Record<string, number>).map(([k, v]) => (
              <li key={k}>
                {k}: {v} documents
              </li>
            ))}
          </ul>
        )}
        <p style={{ marginTop: "0.75rem", fontSize: "0.8rem", color: "var(--muted)" }}>
          Browse via MongoDB Compass: SSH tunnel port 27017 to the container.
        </p>
      </div>
      <UpdatesCard />
      <PowerCard />
    </div>
  );
}

export default function Settings() {
  return (
    <div>
      <h1 className="page-title">Settings</h1>
      <div className="settings-layout">
        <nav className="settings-tabs">
          {TABS.map((tab) => (
            <NavLink
              key={tab.path}
              to={`/settings/${tab.path}`}
              className={({ isActive }) => `settings-tab${isActive ? " active" : ""}`}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
        <div>
          <Routes>
            <Route path="general" element={<GeneralTab />} />
            <Route path="ai-models" element={<AiModelsTab />} />
            <Route path="data-connections" element={<DataConnectionsTab />} />
            <Route path="brokers" element={<BrokersTab />} />
            <Route path="system" element={<SystemTab />} />
            <Route path="*" element={<GeneralTab />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}
