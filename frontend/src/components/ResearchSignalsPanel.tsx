import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ROUTES } from "../lib/routes";
import {
  api,
  type ResearchAssetSignals,
  type ResearchSignal,
  type ResearchSignalItem,
  type ResearchSignalsSnapshot,
} from "../api/client";

const SIGNAL_LABELS: Record<ResearchSignal, string> = {
  buy: "Buy",
  sell: "Sell",
  hold: "Hold",
  mixed: "Mixed",
};

function signalLabel(signal: ResearchSignal | null): string {
  return signal ? SIGNAL_LABELS[signal] : "No signal";
}

function signalBadgeClass(item: ResearchSignalItem): string {
  if (item.status !== "ok" || !item.signal) return "research-signal-badge--none";
  return `research-signal-badge--${item.signal}`;
}

function subtitleParts(item: ResearchSignalItem): string {
  const parts: string[] = [];
  if (item.tone) parts.push(item.tone);
  if (item.approach) parts.push(item.approach);
  return parts.join(" · ");
}

export default function ResearchSignalsPanel() {
  const [snapshot, setSnapshot] = useState<ResearchSignalsSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeClass, setActiveClass] = useState<string | null>(null);

  useEffect(() => {
    api
      .getResearchSignals()
      .then((data) => {
        setSnapshot(data);
        setActiveClass(data.asset_classes[0]?.asset_class ?? null);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load signals"),
      )
      .finally(() => setLoading(false));
  }, []);

  const active = useMemo<ResearchAssetSignals | null>(() => {
    if (!snapshot) return null;
    return (
      snapshot.asset_classes.find((c) => c.asset_class === activeClass) ??
      snapshot.asset_classes[0] ??
      null
    );
  }, [snapshot, activeClass]);

  if (loading) {
    return (
      <section className="research-signals">
        <p className="settings-muted">Loading signals…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="research-signals">
        <p className="settings-error">{error}</p>
      </section>
    );
  }

  if (!snapshot || snapshot.asset_classes.length === 0) {
    return (
      <section className="research-signals">
        <div className="research-signals-header">
          <h2 className="settings-subtitle">Signals</h2>
        </div>
        <p className="settings-muted">
          No asset classes are enabled. Enable one in{" "}
          <Link to="/settings/broker/general">Settings → Broker</Link> to see daily signals.
        </p>
      </section>
    );
  }

  return (
    <section className="research-signals">
      <div className="research-signals-header">
        <h2 className="settings-subtitle">Signals</h2>
        {snapshot.report_date && (
          <span className="research-signals-meta">
            {snapshot.report_filename ? (
              <Link to={ROUTES.research.reportView(snapshot.report_filename)}>
                Daily report · {snapshot.report_date}
              </Link>
            ) : (
              <>Daily report · {snapshot.report_date}</>
            )}
          </span>
        )}
      </div>

      <div className="research-signals-tabs" role="tablist" aria-label="Asset classes">
        {snapshot.asset_classes.map((cls) => {
          const isActive = active?.asset_class === cls.asset_class;
          return (
            <button
              key={cls.asset_class}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={`research-signals-tab${isActive ? " research-signals-tab--active" : ""}`}
              onClick={() => setActiveClass(cls.asset_class)}
            >
              {cls.label}
            </button>
          );
        })}
      </div>

      {active && <SignalsTabPanel snapshot={snapshot} cls={active} />}
    </section>
  );
}

function SignalsTabPanel({
  snapshot,
  cls,
}: {
  snapshot: ResearchSignalsSnapshot;
  cls: ResearchAssetSignals;
}) {
  if (!cls.implemented) {
    return (
      <p className="settings-muted research-signals-empty">
        Daily research is not yet available for {cls.label}.
      </p>
    );
  }

  if (cls.items.length === 0) {
    return (
      <p className="settings-muted research-signals-empty">
        No instruments selected. Choose pairs in{" "}
        <Link to={`/settings/broker/${cls.asset_class}`}>Settings → Broker → {cls.label}</Link>.
      </p>
    );
  }

  if (!snapshot.report_date) {
    return (
      <p className="settings-muted research-signals-empty">
        No daily report yet. Run one from the CLI:{" "}
        <code>brokerai research run-daily --force</code>
      </p>
    );
  }

  return (
    <div className="research-signals-grid">
      {cls.items.map((item) => {
        const subtitle = subtitleParts(item);
        return (
          <div key={item.symbol} className="research-signal-card">
            <div className="research-signal-card-head">
              <span className="research-signal-symbol">{item.symbol}</span>
              <span className={`research-signal-badge ${signalBadgeClass(item)}`}>
                {signalLabel(item.signal)}
              </span>
            </div>
            {item.status === "ok" && subtitle && (
              <span className="research-signal-sub">{subtitle}</span>
            )}
            {item.status === "missing" && (
              <span className="research-signal-sub research-signal-sub--muted">
                Not in latest report
              </span>
            )}
            {item.status === "ok" && item.conviction && (
              <span className="research-signal-conviction">
                {item.conviction} conviction
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
