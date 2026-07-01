import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";

export default function TradesSuggestedPlaceholder() {
  return (
    <div className="trades-coming-soon">
      <h2 className="settings-subtitle">Suggested trades &amp; tips</h2>
      <p className="settings-muted trades-coming-soon-lead">
        Entry suggestions from strategy analysis and exit tips for open positions will appear
        here. Until then, use Live Analysis to inspect recent signals and gate outcomes.
      </p>

      <div className="trades-coming-soon-sections">
        <section className="settings-panel trades-coming-soon-section">
          <h3 className="trades-coming-soon-section-title">Entry suggestions</h3>
          <p className="settings-muted trades-coming-soon-section-desc">
            Signals that passed or were blocked by execution gates.
          </p>
          <div className="research-table-wrap trades-skeleton-table">
            <table className="research-table" aria-hidden="true">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Strategy</th>
                  <th>Pair</th>
                  <th>Direction</th>
                  <th>Suggested action</th>
                </tr>
              </thead>
              <tbody>
                <tr className="trades-skeleton-row">
                  <td colSpan={5}>Coming soon</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section className="settings-panel trades-coming-soon-section">
          <h3 className="trades-coming-soon-section-title">Exit tips</h3>
          <p className="settings-muted trades-coming-soon-section-desc">
            Trailing stop proximity, reverse crossover alerts, and other exit guidance.
          </p>
          <div className="research-table-wrap trades-skeleton-table">
            <table className="research-table" aria-hidden="true">
              <thead>
                <tr>
                  <th>Trade</th>
                  <th>Pair</th>
                  <th>Strategy</th>
                  <th>Urgency</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                <tr className="trades-skeleton-row">
                  <td colSpan={5}>Coming soon</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <Link to="/trading/analysis" className="btn btn-secondary btn-sm trades-coming-soon-link">
        <ExternalLink size={14} aria-hidden="true" />
        Open Live Analysis
      </Link>
    </div>
  );
}
