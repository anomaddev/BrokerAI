import { useEffect, useState, type RefObject } from "react";
import type { IChartApi, UTCTimestamp } from "lightweight-charts";
import type { MarketBoundary } from "../../lib/chart/forexMarketClosures";

export type MarketClosureLineLayout = {
  id: string;
  x: number;
  kind: MarketBoundary["kind"];
  label: string;
};

type MarketClosureOverlayProps = {
  chartRef: RefObject<IChartApi | null>;
  paneRef: RefObject<HTMLDivElement | null>;
  boundaries: MarketBoundary[];
  layoutRevision: number;
};

export default function MarketClosureOverlay({
  chartRef,
  paneRef,
  boundaries,
  layoutRevision,
}: MarketClosureOverlayProps) {
  const [lines, setLines] = useState<MarketClosureLineLayout[]>([]);

  useEffect(() => {
    const chart = chartRef.current;
    const pane = paneRef.current;
    if (!chart || !pane || boundaries.length === 0) {
      setLines([]);
      return;
    }

    let rafId = 0;

    const refresh = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        const timeScale = chart.timeScale();
        const nextLines: MarketClosureLineLayout[] = [];

        for (const boundary of boundaries) {
          const x = timeScale.timeToCoordinate(boundary.time as UTCTimestamp);
          if (x === null) continue;
          nextLines.push({
            id: `${boundary.time}-${boundary.kind}`,
            x,
            kind: boundary.kind,
            label: boundary.label,
          });
        }

        setLines(nextLines);
      });
    };

    refresh();

    const timeScale = chart.timeScale();
    timeScale.subscribeVisibleLogicalRangeChange(refresh);
    const resizeObserver = new ResizeObserver(refresh);
    resizeObserver.observe(pane);

    return () => {
      cancelAnimationFrame(rafId);
      timeScale.unsubscribeVisibleLogicalRangeChange(refresh);
      resizeObserver.disconnect();
    };
  }, [chartRef, paneRef, boundaries, layoutRevision]);

  if (lines.length === 0) return null;

  return (
    <div className="market-closure-overlay" aria-hidden="true">
      {lines.map((line) => (
        <div
          key={line.id}
          className={`market-closure-line market-closure-line--${line.kind}`}
          style={{ left: `${line.x}px` }}
          title={line.label}
        >
          <span className="market-closure-line-label">{line.label}</span>
        </div>
      ))}
    </div>
  );
}
