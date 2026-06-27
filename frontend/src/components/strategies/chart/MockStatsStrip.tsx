import { ChevronDown, ChevronUp } from "lucide-react";

type MockStatsStripProps = {
  expanded: boolean;
  onToggle: () => void;
  lastSignal: string;
  adx: number;
  atr: number;
  confidence: number;
  mockRisk: string;
};

export default function MockStatsStrip({
  expanded,
  onToggle,
  lastSignal,
  adx,
  atr,
  confidence,
  mockRisk,
}: MockStatsStripProps) {
  return (
    <div className={`strategy-stats-strip${expanded ? " strategy-stats-strip--expanded" : ""}`}>
      <button type="button" className="strategy-stats-strip-toggle" onClick={onToggle}>
        <span className="strategy-stats-strip-summary">
          Last signal: {lastSignal} · ADX {adx.toFixed(1)} · ATR {atr.toFixed(4)} · Confidence{" "}
          {confidence}%
        </span>
        {expanded ? (
          <ChevronUp size={16} aria-hidden="true" />
        ) : (
          <ChevronDown size={16} aria-hidden="true" />
        )}
      </button>
      {expanded && (
        <div className="strategy-stats-strip-detail">
          <span>Mock risk per trade: {mockRisk}</span>
          <span className="settings-muted">Visual preview only — no live data</span>
        </div>
      )}
    </div>
  );
}
