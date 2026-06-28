import ParameterCard from "../ParameterCard";
import TimeframeSelect from "../TimeframeSelect";
import LiveSlider from "../LiveSlider";
import { TIMEFRAME_OPTIONS, type Timeframe } from "../../../../lib/strategyParams";

type TimeframeSectionProps = {
  expanded: boolean;
  onToggle: () => void;
  timeframe: Timeframe;
  minCandles: number;
  computedMinCandles: number;
  onTimeframeChange: (value: Timeframe) => void;
  onMinCandlesChange: (value: number) => void;
};

export default function TimeframeSection({
  expanded,
  onToggle,
  timeframe,
  minCandles,
  computedMinCandles,
  onTimeframeChange,
  onMinCandlesChange,
}: TimeframeSectionProps) {
  const minInvalid = minCandles < computedMinCandles || minCandles > 2000;
  const computedExceedsMax = computedMinCandles > 2000;

  return (
    <ParameterCard
      title="Timeframe"
      required
      expanded={expanded}
      onToggle={onToggle}
      badge={!timeframe || minInvalid ? "!" : undefined}
    >
      <TimeframeSelect value={timeframe} options={TIMEFRAME_OPTIONS} onChange={onTimeframeChange} />
      <LiveSlider
        id="min-candles"
        label="Minimum candles required"
        value={minCandles}
        min={computedMinCandles}
        max={2000}
        invalid={minInvalid}
        onChange={onMinCandlesChange}
      />
      {computedExceedsMax ? (
        <p className="param-helper param-helper--warn">
          Computed minimum ({computedMinCandles}) exceeds the maximum allowed (2000). Reduce indicator or filter periods.
        </p>
      ) : minInvalid ? (
        <p className="param-helper param-helper--warn">
          Must be between {computedMinCandles} and 2000 bars.
        </p>
      ) : (
        <p className="param-helper">
          Bars needed before the strategy can run on the next candle ({computedMinCandles}–2000).
        </p>
      )}
    </ParameterCard>
  );
}
