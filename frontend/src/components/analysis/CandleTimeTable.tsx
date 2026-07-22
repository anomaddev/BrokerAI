import { useNavigate } from "react-router-dom";
import type { CandleTimeSummary } from "../../lib/analysis/candleTimeSummaries";
import { buildCandleNavKeys } from "../../lib/analysis/candleTimeNavigation";
import type { CandleNavigationState } from "../../lib/analysis/candleTimeNavigation";
import { ROUTES } from "../../lib/routes";
import { TIMEFRAME_LABELS, type Timeframe } from "../../lib/strategyParams";

function timeframeLabel(timeframe: string): string {
  return TIMEFRAME_LABELS[timeframe as Timeframe] ?? timeframe;
}

type CandleTimeTableProps = {
  summaries: CandleTimeSummary[];
};

function SummaryTags({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <span className="settings-muted">—</span>;
  }

  return (
    <div className="analysis-summary-tags">
      {items.map((item) => (
        <span key={item} className="analysis-summary-tag">
          {item}
        </span>
      ))}
    </div>
  );
}

export default function CandleTimeTable({ summaries }: CandleTimeTableProps) {
  const navigate = useNavigate();
  const candleKeys = buildCandleNavKeys(summaries);

  function openCandle(summary: CandleTimeSummary) {
    navigate(ROUTES.research.analysisCandle(summary.key), {
      state: { candleKeys } satisfies CandleNavigationState,
    });
  }

  return (
    <div className="analysis-candle-table-section">
      <div className="research-table-wrap analysis-table-wrap">
        <table className="research-table research-table--clickable analysis-runs-table analysis-candle-table">
          <thead>
            <tr>
              <th scope="col" className="col-sticky">
                Candle Time
              </th>
              <th scope="col" className="col-hide-sm">
                Source
              </th>
              <th scope="col">TFs</th>
              <th scope="col">Assets</th>
              <th scope="col">Strategies</th>
            </tr>
          </thead>
          <tbody>
            {summaries.map((summary) => {
              const rowClassName = [
                summary.isCurrentBar ? "analysis-runs-table-row--current-bar" : undefined,
              ]
                .filter(Boolean)
                .join(" ");

              return (
                <tr
                  key={summary.key}
                  className={rowClassName || undefined}
                  onClick={() => openCandle(summary)}
                >
                  <td className="col-sticky">
                    <span className="analysis-candle-time-cell">
                      <span>{summary.label}</span>
                      {summary.exitMonitorTradeCount > 0 ? (
                        <span className="analysis-candle-exit-badge">
                          {summary.exitMonitorTradeCount} exit
                          {summary.exitMonitorTradeCount === 1 ? "" : "s"}
                        </span>
                      ) : null}
                    </span>
                  </td>
                  <td className="col-hide-sm">
                    <SummaryTags items={summary.sources} />
                  </td>
                  <td>
                    <SummaryTags items={summary.timeframes.map(timeframeLabel)} />
                  </td>
                  <td>
                    <SummaryTags items={summary.assetClasses} />
                  </td>
                  <td className="analysis-candle-strategy-count">{summary.strategyCount}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
