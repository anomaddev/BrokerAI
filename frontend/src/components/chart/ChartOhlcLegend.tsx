import type { OhlcSnapshot } from "../../lib/chart/useCandleCrosshairOhlc";
import { formatChartPrice } from "../../lib/chart/formatChartPrice";
import { formatAppInstant, type TimeFormatOptions } from "../../lib/formatTime";

type ChartOhlcLegendProps = {
  snapshot: OhlcSnapshot | null;
  timeOptions: TimeFormatOptions;
};

function OhlcValue({ label, value, tone }: { label: string; value: number; tone?: "up" | "down" }) {
  return (
    <span className={`chart-ohlc-legend-item chart-ohlc-legend-item--${tone ?? "neutral"}`}>
      <span className="chart-ohlc-legend-key">{label}</span>
      {formatChartPrice(value)}
    </span>
  );
}

export default function ChartOhlcLegend({ snapshot, timeOptions }: ChartOhlcLegendProps) {
  if (!snapshot) {
    return <div className="chart-ohlc-legend chart-ohlc-legend--empty">Hover chart for OHLC</div>;
  }

  const closeTone = snapshot.close >= snapshot.open ? "up" : "down";
  const timeLabel = formatAppInstant(snapshot.time * 1000, timeOptions, "short");

  return (
    <div className="chart-ohlc-legend">
      <span className="chart-ohlc-legend-time">{timeLabel}</span>
      <OhlcValue label="O" value={snapshot.open} />
      <OhlcValue label="H" value={snapshot.high} tone="up" />
      <OhlcValue label="L" value={snapshot.low} tone="down" />
      <OhlcValue label="C" value={snapshot.close} tone={closeTone} />
    </div>
  );
}
