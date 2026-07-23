import { useEffect, useRef, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import {
  api,
  type DomainSettingsConfig,
  type UpdateSettingsConfig,
  type UpdateStatusResponse,
} from "../api/client";
import useAutoSave from "../hooks/useAutoSave";
import { formatBotName, sortBots } from "../lib/bots";
import AssetClassTab from "./settings/AssetClassTab";
import AccountTab from "./settings/AccountTab";
import BackupTab from "./settings/BackupTab";
import DisplayTab from "./settings/DisplayTab";
import BrokerGeneralTab from "./settings/BrokerGeneralTab";
import GeneralTab from "./settings/GeneralTab";
import DataConnectionsTabComponent from "./settings/DataConnectionsTab";
import ModelsTab from "./settings/ModelsTab";
import ReportsTab from "./settings/ReportsTab";
import ResearchDataTab from "./settings/ResearchDataTab";
import BacktestingTab from "./settings/BacktestingTab";
import AiStrategiesTab from "./settings/AiStrategiesTab";
import SettingsPanelHeader from "../components/SettingsPanelHeader";

type SettingsNavItem = {
  path: string;
  label: string;
};

type SettingsNavSection = {
  label: string;
  items: SettingsNavItem[];
};

const SETTINGS_SECTIONS: SettingsNavSection[] = [
  {
    label: "General",
    items: [
      { path: "general", label: "General" },
      { path: "account", label: "Account" },
      { path: "display", label: "Display" },
    ],
  },
  {
    label: "Data",
    items: [
      { path: "models", label: "Models" },
      { path: "connections", label: "Connections" },
    ],
  },
  {
    label: "Research",
    items: [
      { path: "reports", label: "Reports" },
      { path: "data", label: "Data" },
      { path: "backtesting", label: "Backtesting" },
      { path: "ai-strategies", label: "AI Startup" },
    ],
  },
  {
    label: "Broker",
    items: [
      { path: "broker/general", label: "General" },
      { path: "broker/forex", label: "Forex" },
      { path: "broker/metals", label: "Precious Metals" },
      { path: "broker/stocks", label: "Stocks" },
      { path: "broker/crypto", label: "Crypto" },
      { path: "broker/futures", label: "Futures" },
      { path: "broker/options", label: "Options" },
    ],
  },
  {
    label: "System",
    items: [
      { path: "system", label: "System" },
      { path: "backup", label: "Backup" },
    ],
  },
];

type BotStatus = { name: string; state: string; last_error?: string | null };

function stateBadgeClass(state: string): string {
  if (state === "running" || state === "stopped" || state === "error") return state;
  return "stopped";
}

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
  { value: "next-major", label: "Up to next major release" },
];

function parseSemverMajor(ref?: string | null): number | null {
  if (!ref) return null;
  const match = ref.replace(/^v/i, "").match(/^(\d+)/);
  return match ? Number(match[1]) : null;
}

function computeConfiguredPin(
  config: Pick<UpdateSettingsConfig, "update_track" | "branch" | "release">,
  installedRef?: string | null,
): string {
  if (config.update_track === "branch") return `branch:${config.branch || "main"}`;
  if (config.update_track === "release") {
    const tag = config.release || "unset";
    return `release:${tag.replace(/^v/, "")}`;
  }
  if (config.update_track === "next-major") {
    const major = parseSemverMajor(installedRef);
    return major != null ? `next-major:${major}.x` : "next-major";
  }
  return "latest-release";
}

function configuredTargetInfo(
  config: Pick<UpdateSettingsConfig, "update_track" | "branch" | "release">,
  installedRef?: string | null,
) {
  if (config.update_track === "branch") {
    return { track: "branch", ref: config.branch || "main" };
  }
  if (config.update_track === "release") {
    return { track: "release", ref: (config.release || "unset").replace(/^v/, "") };
  }
  if (config.update_track === "next-major") {
    const major = parseSemverMajor(installedRef);
    return { track: "next-major", ref: major != null ? `${major}.x` : "same major" };
  }
  return { track: "latest-release", ref: "latest" };
}

function checkMatchesConfig(
  data: UpdateStatusResponse | null,
  config: UpdateSettingsConfig | null,
): boolean {
  if (!data || !config) return false;
  if (data.update_track !== config.update_track) return false;
  if (config.update_track === "branch") {
    return (data.branch ?? "main") === (config.branch || "main");
  }
  if (config.update_track === "release") {
    return (data.release ?? "") === config.release;
  }
  return true;
}

function checkResultsMatchConfig(
  data: UpdateStatusResponse | null,
  config: UpdateSettingsConfig | null,
): boolean {
  if (!data || !config) return false;
  if (checkMatchesConfig(data, config)) return true;
  return data.check?.update_track === config.update_track;
}

function installedInfoRef(data: UpdateStatusResponse | null): string | null {
  if (!data) return null;
  return data.check?.installed?.ref ?? data.installed_ref ?? null;
}

function isTrackConfigPatch(patch: Partial<UpdateSettingsConfig>): boolean {
  return patch.update_track !== undefined || patch.branch !== undefined;
}

type UpdatesDebugSnapshot = {
  label: string;
  config: UpdateSettingsConfig | null;
  update: UpdateStatusResponse | null;
  checkError: string | null;
  flags?: Record<string, unknown>;
};

function logUpdatesDebug({ label, config, update, checkError, flags }: UpdatesDebugSnapshot) {
  if (!import.meta.env.DEV) return;
  console.groupCollapsed(`[BrokerAI Updates] ${label}`);
  console.log("config", config);
  console.log("update response", update);
  console.log("checkError state", checkError);
  if (update) {
    console.log("resolveCheckError", resolveCheckError(update));
    console.log("checkMatchesConfig", checkMatchesConfig(update, config));
    console.log("checkResultsMatchConfig", checkResultsMatchConfig(update, config));
  }
  if (flags) console.log("derived", flags);
  console.groupEnd();
}


function resolveCheckError(data: UpdateStatusResponse | null): string | null {
  if (!data) return null;
  if (data.check_error) return data.check_error;
  if (isDowngradeBlocked(data)) return null;

  if (data.checked && data.update_available == null) {
    const msg = data.message?.trim();
    if (!msg) return null;
    const benign = new Set([
      "Local dev — checking uses git; applying updates is simulated only",
      "Up to date",
      "Update available",
    ]);
    if (!benign.has(msg) && !msg.includes("Downgrades are not allowed")) return msg;
  }

  return null;
}

function isDowngradeBlocked(data: UpdateStatusResponse | null): boolean {
  if (!data) return false;
  if (data.downgrade_blocked === true) return true;
  return data.check?.status === "downgrade-blocked";
}

function downgradeBlockedMessage(data: UpdateStatusResponse | null): string | null {
  if (!isDowngradeBlocked(data)) return null;
  return (
    data?.check?.message?.trim() ||
    data?.message?.trim() ||
    "Configured target is older than installed. Downgrades are not allowed."
  );
}

function isNoReleasesError(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    lower.includes("no github releases") ||
    lower.includes("no releases or tags") ||
    lower.includes("could not resolve latest github release") ||
    lower.includes("could not resolve next-major") ||
    lower.includes("could not determine installed semver")
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
  const [updating, setUpdating] = useState(false);
  const [errorOverlay, setErrorOverlay] = useState<ErrorOverlayState | null>(null);
  const configRef = useRef<UpdateSettingsConfig | null>(null);
  const userEditedRef = useRef(false);

  function showErrorOverlay(title: string, message: string) {
    setErrorOverlay({ title, message });
  }

  function canPersistConfig(next: UpdateSettingsConfig): boolean {
    if (next.update_track === "branch" && !next.branch.trim()) return false;
    if (next.update_track === "release" && !next.release.trim()) return false;
    return true;
  }

  function applySavedConfig(saved: UpdateSettingsConfig) {
    configRef.current = saved;
    setConfig(saved);
  }

  function applyUpdateData(data: UpdateStatusResponse, source = "applyUpdateData") {
    setUpdate(data);
    const checkErr = resolveCheckError(data);
    setCheckError(checkErr);
    logUpdatesDebug({
      label: source,
      config: configRef.current,
      update: data,
      checkError: checkErr,
    });
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
        configured_pin: configRef.current
          ? computeConfiguredPin(configRef.current, prev.installed_ref)
          : prev.configured_pin,
        update_track: configRef.current?.update_track ?? prev.update_track,
        branch: configRef.current?.branch ?? prev.branch,
        release: configRef.current?.release ?? prev.release,
        check: null,
        update_available: null,
        checked: false,
      };
    });
  }

  const loadStatus = () =>
    api
      .updateStatus()
      .then((data) => {
        applyUpdateData(data, "loadStatus");
      })
      .catch((err: Error) => showErrorOverlay("Update status unavailable", err.message));

  const runCheck = async () => {
    setChecking(true);
    try {
      const data = await api.checkForUpdate();
      applyUpdateData(data, "runCheck");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Update check failed";
      setCheckError(message);
      logUpdatesDebug({
        label: "runCheck error",
        config: configRef.current,
        update,
        checkError: message,
      });
      showErrorOverlay(checkErrorTitle(message), message);
    } finally {
      setChecking(false);
    }
  };

  const { saving, saveNow, scheduleSave, markReady, markNotReady } = useAutoSave({
    defaultDebounceMs: 150,
    canSave: () => {
      const snapshot = configRef.current;
      return Boolean(snapshot?.config_writable && canPersistConfig(snapshot));
    },
    onSave: async () => {
      const snapshot = configRef.current;
      if (!snapshot?.config_writable || !canPersistConfig(snapshot)) return;

      try {
        const saved = await api.saveUpdateSettings({
          update_track: snapshot.update_track,
          branch: snapshot.branch,
          release: snapshot.release,
          auto_update: snapshot.auto_update,
        });
        applySavedConfig(saved);
        await runCheck();
      } catch (err) {
        showErrorOverlay(
          "Failed to save settings",
          err instanceof Error ? err.message : "Failed to save settings",
        );
        throw err;
      }
    },
  });

  useEffect(() => {
    let cancelled = false;

    async function init() {
      setLoading(true);
      try {
        const settingsData = await api.getUpdateSettings();
        if (cancelled) return;

        userEditedRef.current = false;
        configRef.current = settingsData;
        setConfig(settingsData);
        markReady();

        const checkData = await api.checkForUpdate();
        if (!cancelled) {
          applyUpdateData(checkData, "init");
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
      markNotReady();
    };
  }, [markNotReady, markReady]);

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

  function applyConfig(patch: Partial<UpdateSettingsConfig>, debounceMs = 0) {
    userEditedRef.current = true;
    const trackChanged = isTrackConfigPatch(patch);
    setConfig((current) => {
      if (!current) return current;
      const next = { ...current, ...patch };
      if (patch.update_track === "release") {
        next.auto_update = false;
      }
      configRef.current = next;
      return next;
    });
    const next = configRef.current;
    if (!next) return;
    if (trackChanged) {
      invalidateVersionMeta();
      saveNow();
      return;
    }
    if (patch.release !== undefined) {
      invalidateVersionMeta();
    }
    scheduleSave(debounceMs > 0 ? debounceMs : undefined);
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
  const checkResultsFresh = checkResultsMatchConfig(update, config);
  const resolvedCheckError = checkResultsFresh ? (checkError ?? resolveCheckError(update)) : null;
  const installedInfo = checkResultsFresh && update?.check?.installed
    ? update.check.installed
    : {
        track: update?.installed_track,
        ref: update?.installed_ref,
        commit_short: update?.installed_version,
      };
  const availableInfo = checkResultsFresh ? update?.check?.available : undefined;
  const installedRef = installedInfo?.ref ?? update?.installed_ref;
  const targetInfo = availableInfo ?? (config ? configuredTargetInfo(config, installedRef) : undefined);
  const updateAvailable = checkResultsFresh && update?.update_available === true;
  const downgradeBlocked = checkResultsFresh && isDowngradeBlocked(update);
  const downgradeMessage = downgradeBlocked ? downgradeBlockedMessage(update) : null;
  const hasChecked = checkResultsFresh && update?.checked === true;
  const showInstalled = hasVersionInfo(installedInfo);
  const showTarget = Boolean(config && targetInfo);
  const formDisabled = loading || saving || !config?.config_writable;
  const repoDisplay = config?.repo?.replace(/^https?:\/\//, "") ?? "—";

  const displayStatus = loading || checking
    ? "checking"
    : resolvedCheckError
      ? "check_error"
      : status === "running"
        ? "running"
        : updateAvailable
          ? "update_available"
          : downgradeBlocked
            ? "downgrade_blocked"
          : hasChecked && update?.update_available === false
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
    update_available: "Update available",
    downgrade_blocked: "Downgrade blocked",
  };

  const actionsDisabled = loading || checking || saving || updating || status === "running";

  useEffect(() => {
    logUpdatesDebug({
      label: "render state",
      config,
      update,
      checkError,
      flags: {
        loading,
        checking,
        saving,
        checkFresh,
        checkResultsFresh,
        resolvedCheckError,
        updateAvailable,
        downgradeBlocked,
        downgradeMessage,
        hasChecked,
        displayStatus,
        installedInfo,
        availableInfo,
        targetInfo,
        showInstalled,
        showTarget,
      },
    });
  }, [
    config?.update_track,
    config?.branch,
    config?.release,
    config?.configured_pin,
    update?.configured_pin,
    update?.update_track,
    update?.update_available,
    update?.checked,
    update?.check_error,
    update?.check?.available?.ref,
    update?.check?.available?.commit_short,
    update?.check?.installed?.ref,
    checkError,
    loading,
    checking,
    saving,
    checkFresh,
    checkResultsFresh,
    resolvedCheckError,
    updateAvailable,
    downgradeBlocked,
    hasChecked,
    displayStatus,
    showInstalled,
    showTarget,
  ]);

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
              value={(config ?? configRef.current)?.update_track ?? "branch"}
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
              placeholder="0.0.7"
              onChange={(e) => applyConfig({ release: e.target.value }, 2000)}
            />
          </div>
        ) : null}

        {config?.update_track !== "release" ? (
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
        ) : null}

        {resolvedCheckError ? (
          <div className="update-alert update-alert--error" role="alert">
            <strong>{checkErrorTitle(resolvedCheckError)}</strong>
            <p>{resolvedCheckError}</p>
          </div>
        ) : null}

        {downgradeMessage ? (
          <div className="update-alert update-alert--warning" role="status">
            <strong>Downgrade blocked</strong>
            <p>{downgradeMessage}</p>
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
        {update?.message && !loading && !checking && !resolvedCheckError && !downgradeBlocked ? (
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

function DomainCard() {
  const [config, setConfig] = useState<DomainSettingsConfig | null>(null);
  const [domain, setDomain] = useState("");
  const [supabaseDomain, setSupabaseDomain] = useState("");
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getDomainSettings()
      .then((data) => {
        if (cancelled) return;
        setConfig(data);
        setDomain(data.domain || "");
        setSupabaseDomain(data.supabase_domain || "");
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load domain settings");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleApply() {
    setApplying(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await api.applyDomainSettings({
        domain: domain.trim(),
        supabase_domain: supabaseDomain.trim(),
      });
      setConfig(saved);
      setDomain(saved.domain || "");
      setSupabaseDomain(saved.supabase_domain || "");
      setMessage(saved.message || "Domain settings applied.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply domain settings");
    } finally {
      setApplying(false);
    }
  }

  const canApply = Boolean(domain.trim()) && !applying && !loading;

  return (
    <div className="card">
      <h3>Public domains (HTTPS)</h3>
      <p style={{ color: "var(--muted)", fontSize: "0.9rem", marginBottom: "0.75rem" }}>
        Set hostnames after DNS A/AAAA records point at this host and ports 80/443 are open.
        Apply installs host Caddy (Let&apos;s Encrypt) for BrokerAI and optionally public
        Supabase (Kong + Studio with basic auth).
      </p>
      {loading ? (
        <p style={{ color: "var(--muted)", fontSize: "0.875rem" }}>Loading…</p>
      ) : (
        <>
          {config?.dev_mode ? (
            <p className="update-dev-note">
              Local/dev saves the hostnames to {config.config_path} only — Caddy TLS is applied
              on Proxmox/LXC installs.
            </p>
          ) : null}
          {!config?.apply_available && !config?.dev_mode ? (
            <p className="update-readonly-note">
              Domain apply is unavailable on this host (missing apply script or sudo). Edit{" "}
              {config?.config_path ?? "/etc/brokerai/config.env"} and run the Caddy install helper
              instead.
            </p>
          ) : null}
          <div className="update-config-form">
            <div className="field">
              <label htmlFor="brokerai-domain">BrokerAI hostname</label>
              <input
                id="brokerai-domain"
                type="text"
                value={domain}
                placeholder="broker.example.com"
                autoComplete="off"
                spellCheck={false}
                disabled={applying || (!config?.apply_available && !config?.dev_mode)}
                onChange={(e) => setDomain(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="supabase-domain">Supabase hostname (optional)</label>
              <input
                id="supabase-domain"
                type="text"
                value={supabaseDomain}
                placeholder="supabase.example.com"
                autoComplete="off"
                spellCheck={false}
                disabled={applying || (!config?.apply_available && !config?.dev_mode)}
                onChange={(e) => setSupabaseDomain(e.target.value)}
              />
            </div>
            {config?.supabase_url ? (
              <p className="update-readonly-note" style={{ marginBottom: 0 }}>
                Current Kong URL: <code>{config.supabase_url}</code>
              </p>
            ) : null}
          </div>
          {error ? (
            <div className="update-alert update-alert--error" role="alert">
              {error}
            </div>
          ) : null}
          {message ? (
            <div className="update-alert update-alert--success" role="status">
              {message}
            </div>
          ) : null}
          <div className="update-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={!canApply || (!config?.apply_available && !config?.dev_mode)}
              onClick={() => void handleApply()}
            >
              {applying ? "Applying…" : "Apply HTTPS domains"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function SystemTab() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [bots, setBots] = useState<BotStatus[]>([]);
  const [db, setDb] = useState<Record<string, unknown> | null>(null);
  const [restartingBot, setRestartingBot] = useState<string | null>(null);
  const [botActionError, setBotActionError] = useState<string | null>(null);

  async function refreshBots() {
    try {
      const data = await api.bots();
      setBots(data.bots);
    } catch {
      setBots([]);
    }
  }

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    void refreshBots();
    api.dbStats().then(setDb).catch(() => setDb(null));
  }, []);

  const postgres = health?.postgres as { status?: string } | undefined;
  const orchestratorRunning = Boolean(health?.orchestrator_running);
  const sortedBots = sortBots(bots);

  async function refreshHealthAndBots() {
    await refreshBots();
    try {
      const nextHealth = await api.health();
      setHealth(nextHealth);
    } catch {
      /* keep prior health */
    }
  }

  async function handleRestartBot(name: string) {
    if (!orchestratorRunning || restartingBot) return;
    setBotActionError(null);
    setRestartingBot(name);
    try {
      await api.restartBot(name);
      // Heartbeat can lag a few seconds after control IPC.
      await new Promise((resolve) => window.setTimeout(resolve, 800));
      await refreshHealthAndBots();
    } catch (err) {
      setBotActionError(err instanceof Error ? err.message : `Failed to restart ${formatBotName(name)}.`);
      await refreshBots();
    } finally {
      setRestartingBot(null);
    }
  }

  async function handleRestartOrchestrator() {
    if (restartingBot) return;
    setBotActionError(null);
    setRestartingBot("__orchestrator__");
    try {
      const result = await api.restartOrchestrator();
      // systemd bounce needs a bit longer before heartbeat is fresh.
      await new Promise((resolve) =>
        window.setTimeout(resolve, result.mode === "systemd" ? 2500 : 1000),
      );
      await refreshHealthAndBots();
    } catch (err) {
      setBotActionError(err instanceof Error ? err.message : "Failed to restart orchestrator.");
      await refreshHealthAndBots();
    } finally {
      setRestartingBot(null);
    }
  }

  const actionBusy = restartingBot != null;
  const orchestratorBusy = restartingBot === "__orchestrator__";

  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title="System"
        description="Health, database status, public domains, software updates, and power controls."
      />
      <div className="settings-panel-body settings-panel-body--stack">
      <div className="card">
        <h3>System Status</h3>
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          Version: {String(health?.version ?? "—")} · Postgres: {postgres?.status ?? "unknown"}
        </p>
        <p style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: "0.35rem" }}>
          Restart the orchestrator or a single module without rebooting the API or host.
        </p>
        {botActionError ? <p className="settings-error">{botActionError}</p> : null}
        <div className="system-status-bots">
          <div className="system-status-bot">
            <div className="system-status-bot__info">
              <div className="system-status-bot__row">
                <span className="system-status-bot__name">Orchestrator</span>
                <span className={`badge ${orchestratorRunning ? "running" : "stopped"}`}>
                  {orchestratorRunning ? "running" : "offline"}
                </span>
              </div>
              <p className="system-status-bot__hint">
                Restarts all trading modules. On production hosts this bounces the
                orchestrator service.
              </p>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={actionBusy}
              onClick={() => void handleRestartOrchestrator()}
              title="Restart orchestrator"
            >
              {orchestratorBusy ? "Restarting…" : "Restart"}
            </button>
          </div>
          {sortedBots.length === 0 ? (
            <p style={{ color: "var(--muted)", fontSize: "0.875rem" }}>No sub-bots configured.</p>
          ) : (
            sortedBots.map((bot) => {
              const errorText = bot.last_error?.trim() || null;
              const busy = restartingBot === bot.name;
              return (
                <div key={bot.name} className="system-status-bot">
                  <div className="system-status-bot__info">
                    <div className="system-status-bot__row">
                      <span className="system-status-bot__name">{formatBotName(bot.name)}</span>
                      <span className={`badge ${stateBadgeClass(bot.state)}`}>{bot.state}</span>
                    </div>
                    {errorText ? (
                      <p className="system-status-bot__error" title={errorText}>
                        {errorText}
                      </p>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={!orchestratorRunning || actionBusy}
                    onClick={() => void handleRestartBot(bot.name)}
                    title={
                      orchestratorRunning
                        ? `Restart ${formatBotName(bot.name)}`
                        : "Orchestrator is offline"
                    }
                  >
                    {busy ? "Restarting…" : "Restart"}
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
      <div className="card">
        <h3>Postgres</h3>
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          Database: {String(db?.database ?? "—")}
          {typeof db?.uri === "string" && db.uri ? ` · ${db.uri}` : ""}
        </p>
        {db?.tables && (
          <ul style={{ marginTop: "0.5rem", paddingLeft: "1.25rem", color: "var(--muted)" }}>
            {Object.entries(db.tables as Record<string, number>).map(([k, v]) => (
              <li key={k}>
                {k}: {v} rows
              </li>
            ))}
          </ul>
        )}
        <p style={{ marginTop: "0.75rem", fontSize: "0.8rem", color: "var(--muted)" }}>
          Self-hosted Supabase Postgres (schema <code>brokerai</code>). Studio:{" "}
          <code>http://127.0.0.1:3000</code> (or your public Supabase hostname when configured).
        </p>
      </div>
      <DomainCard />
      <UpdatesCard />
      <PowerCard />
      </div>
    </div>
  );
}

export default function Settings() {
  return (
    <div className="settings-page">
      <div className="settings-layout">
        <div className="settings-nav-column">
          <h1 className="page-title settings-page-title">Settings</h1>
          <nav className="settings-tabs" aria-label="Settings sections">
          {SETTINGS_SECTIONS.map((section) => {
            const showSectionLabel =
              section.items.length > 1 ||
              (section.items.length === 1 && section.items[0].label !== section.label);

            return (
            <div key={section.label} className="settings-nav-section">
              {showSectionLabel && (
                <span className="settings-section-label">{section.label}</span>
              )}
              {section.items.map((item) => (
                <NavLink
                  key={item.path}
                  to={`/settings/${item.path}`}
                  className={({ isActive }) => `settings-tab${isActive ? " active" : ""}`}
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
            );
          })}
        </nav>
        </div>
        <div className="settings-content">
          <Routes>
            <Route index element={<Navigate to="general" replace />} />
            <Route path="general" element={<GeneralTab />} />
            <Route path="account" element={<AccountTab />} />
            <Route path="display" element={<DisplayTab />} />
            <Route path="models" element={<ModelsTab />} />
            <Route path="reports" element={<ReportsTab />} />
            <Route path="data" element={<ResearchDataTab />} />
            <Route path="backtesting" element={<BacktestingTab />} />
            <Route path="ai-strategies" element={<AiStrategiesTab />} />
            <Route path="connections" element={<DataConnectionsTabComponent />} />
            <Route path="broker/general" element={<BrokerGeneralTab />} />
            <Route path="broker/forex" element={<AssetClassTab assetClass="forex" label="Forex" />} />
            <Route
              path="broker/metals"
              element={<AssetClassTab assetClass="metals" label="Precious Metals" />}
            />
            <Route path="broker/stocks" element={<AssetClassTab assetClass="stocks" label="Stocks" />} />
            <Route path="broker/crypto" element={<AssetClassTab assetClass="crypto" label="Crypto" />} />
            <Route path="broker/futures" element={<AssetClassTab assetClass="futures" label="Futures" />} />
            <Route path="broker/options" element={<AssetClassTab assetClass="options" label="Options" />} />
            <Route path="broker" element={<Navigate to="/settings/broker/general" replace />} />
            <Route path="system" element={<SystemTab />} />
            <Route path="backup" element={<BackupTab />} />
            <Route path="*" element={<GeneralTab />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}
