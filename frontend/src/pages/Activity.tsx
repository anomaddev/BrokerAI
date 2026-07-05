import { useEffect, useState } from "react";
import { api, type BotActivityEvent } from "../api/client";
import { activityTimelineDetail, activityTimelineLabel } from "../lib/botActivity";
import { useGeneralSettings } from "../hooks/useGeneralSettings";

const POLL_INTERVAL_MS = 15_000;
const ACTIVITY_LIMIT = 100;

export default function Activity() {
  const { formatInstant } = useGeneralSettings();
  const [events, setEvents] = useState<BotActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await api.getBotActivity(ACTIVITY_LIMIT);
        if (!cancelled) {
          setEvents(data.events);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load activity");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const interval = window.setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <div>
      <h1 className="page-title">Activity</h1>
      <div className="settings-panel">
        {loading && <p className="settings-muted">Loading activity…</p>}
        {error && !loading && <p className="settings-error">{error}</p>}
        {!loading && !error && events.length === 0 && (
          <p className="settings-muted">No activity recorded yet.</p>
        )}
        {!loading && !error && events.length > 0 && (
          <div className="research-table-wrap">
            <table className="research-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Event</th>
                  <th>Detail</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id}>
                    <td className="settings-muted">{formatInstant(event.occurred_at)}</td>
                    <td>{activityTimelineLabel(event)}</td>
                    <td>{activityTimelineDetail(event) ?? "—"}</td>
                    <td className="settings-muted">{event.source ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
