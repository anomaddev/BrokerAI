import { useEffect, useState } from "react";
import { api } from "../api/client";
import { formatUptime, uptimeMsSince } from "../lib/uptime";
import BotStatusBar from "./BotStatusBar";

const UPTIME_REFRESH_MS = 1_000;
const UPTIME_SYNC_MS = 15_000;

type SidebarStatusPanelProps = {
  collapsed: boolean;
};

export default function SidebarStatusPanel({ collapsed }: SidebarStatusPanelProps) {
  const [orchestratorRunning, setOrchestratorRunning] = useState<boolean | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [uptimeLabel, setUptimeLabel] = useState("—");
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (collapsed) return undefined;

    let cancelled = false;
    let syncTimer: number | undefined;

    async function sync() {
      try {
        const health = await api.health();
        if (cancelled) return;
        setOrchestratorRunning(Boolean(health.orchestrator_running));
        setStartedAt(
          health.orchestrator_running && health.orchestrator_started_at
            ? health.orchestrator_started_at
            : null,
        );
      } catch {
        if (!cancelled) {
          setOrchestratorRunning(false);
          setStartedAt(null);
        }
      }
    }

    function scheduleSync() {
      syncTimer = window.setTimeout(() => {
        void sync().finally(() => {
          if (!cancelled) scheduleSync();
        });
      }, UPTIME_SYNC_MS);
    }

    void sync();
    scheduleSync();

    return () => {
      cancelled = true;
      if (syncTimer !== undefined) window.clearTimeout(syncTimer);
    };
  }, [collapsed]);

  useEffect(() => {
    if (collapsed) return undefined;

    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, UPTIME_REFRESH_MS);

    return () => window.clearInterval(timer);
  }, [collapsed]);

  useEffect(() => {
    const uptimeMs = uptimeMsSince(startedAt, now);
    setUptimeLabel(uptimeMs != null ? formatUptime(uptimeMs) : "—");
  }, [startedAt, now]);

  if (collapsed) {
    return null;
  }

  return (
    <>
      <div className="sidebar-status-header">
        <span className="sidebar-section-label">Status</span>
        <span className="sidebar-status-uptime" title="Orchestrator uptime">
          {uptimeLabel}
        </span>
      </div>
      <div className="sidebar-status-panel">
        <BotStatusBar orchestratorRunning={orchestratorRunning} />
      </div>
    </>
  );
}
