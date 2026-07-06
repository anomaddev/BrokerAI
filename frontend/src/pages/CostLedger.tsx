import { useCallback, useEffect, useState } from "react";
import { api, type CostLedgerEntry, type CostLedgerSummary } from "../api/client";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import {
  SUMMARY_PERIOD_OPTIONS,
  costCategoryLabel,
  costEntryDetail,
  formatCostUsd,
  sourceLabel,
  summaryPeriodRange,
  type CostSummaryPeriod,
} from "../lib/costLedger";

const POLL_INTERVAL_MS = 15_000;
const LEDGER_LIMIT = 100;

export default function CostLedger() {
  const { formatInstant } = useGeneralSettings();
  const [entries, setEntries] = useState<CostLedgerEntry[]>([]);
  const [summary, setSummary] = useState<CostLedgerSummary | null>(null);
  const [period, setPeriod] = useState<CostSummaryPeriod>("7d");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const range = summaryPeriodRange(period);
    const [ledgerData, summaryData] = await Promise.all([
      api.getCostLedger({ limit: LEDGER_LIMIT }),
      api.getCostLedgerSummary(range),
    ]);
    setEntries(ledgerData.items);
    setSummary(summaryData);
    setError(null);
  }, [period]);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      try {
        await load();
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load cost ledger");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    setLoading(true);
    run();
    const interval = window.setInterval(() => {
      load().catch(() => undefined);
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [load]);

  return (
    <div>
      <h1 className="page-title">Cost Ledger</h1>

      <div className="settings-panel" style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
          {SUMMARY_PERIOD_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              className={`btn ${period === option.id ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setPeriod(option.id)}
            >
              {option.label}
            </button>
          ))}
          <span className="settings-muted" style={{ marginLeft: "auto" }}>
            Total: {formatCostUsd(summary?.grand_total_usd ?? 0)}
            {summary?.totals?.[0]?.count != null ? ` (${summary.totals.reduce((n, t) => n + t.count, 0)} entries)` : ""}
          </span>
        </div>
      </div>

      <div className="settings-panel">
        {loading && <p className="settings-muted">Loading cost ledger…</p>}
        {error && !loading && <p className="settings-error">{error}</p>}
        {!loading && !error && entries.length === 0 && (
          <p className="settings-muted">No costs recorded yet.</p>
        )}
        {!loading && !error && entries.length > 0 && (
          <div className="research-table-wrap">
            <table className="research-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Category</th>
                  <th>Cost</th>
                  <th>Description</th>
                  <th>Source</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="settings-muted">{formatInstant(entry.occurred_at)}</td>
                    <td>{costCategoryLabel(entry.category)}</td>
                    <td>{formatCostUsd(entry.amount_usd)}</td>
                    <td>{entry.description}</td>
                    <td className="settings-muted">{sourceLabel(entry.source)}</td>
                    <td className="settings-muted">{costEntryDetail(entry) ?? "—"}</td>
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
