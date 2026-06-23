import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "../api/client";

const TABS = [
  { path: "general", label: "General" },
  { path: "ai-models", label: "AI Models" },
  { path: "data-connections", label: "Data Connections" },
  { path: "brokers", label: "Brokers" },
  { path: "system", label: "System" },
];

const SUB_BROKERS = ["Crypto", "Forex", "Stocks", "Futures", "Options"];

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

function SystemTab() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [db, setDb] = useState<Record<string, unknown> | null>(null);
  const [update, setUpdate] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.dbStats().then(setDb).catch(() => setDb(null));
    api.updateStatus().then(setUpdate).catch(() => setUpdate(null));
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
      <div className="card">
        <h3>Updates</h3>
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          Track: {String(update?.configured_pin ?? "—")} · Installed:{" "}
          {String(update?.installed_version ?? "—")}
        </p>
        <button
          className="btn"
          type="button"
          style={{ marginTop: "0.75rem" }}
          onClick={() => api.triggerUpdate().catch(() => undefined)}
        >
          Update now
        </button>
      </div>
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
