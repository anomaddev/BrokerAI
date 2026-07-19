import ParameterCard from "../ParameterCard";
import TimeframeSelect from "../TimeframeSelect";
import LiveSlider from "../LiveSlider";
import {
  MIN_CANDLES_SLIDER_MAX,
  MIN_CANDLES_SLIDER_MIN,
  TIMEFRAME_LABELS,
  TIMEFRAME_OPTIONS,
  formatCandleLookback,
  type Timeframe,
} from "../../../../lib/strategyParams";

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
  const belowComputedMin = minCandles < computedMinCandles;
  const outOfRange =
    minCandles < MIN_CANDLES_SLIDER_MIN || minCandles > MIN_CANDLES_SLIDER_MAX;
  const minInvalid = outOfRange || belowComputedMin || computedMinCandles > MIN_CANDLES_SLIDER_MAX;
  const computedExceedsMax = computedMinCandles > MIN_CANDLES_SLIDER_MAX;

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
        min={MIN_CANDLES_SLIDER_MIN}
        max={MIN_CANDLES_SLIDER_MAX}
        step={10}
        invalid={minInvalid}
        onChange={onMinCandlesChange}
      />
      {computedExceedsMax ? (
        <p className="param-helper param-helper--warn">
          Computed minimum ({computedMinCandles}) exceeds the maximum allowed (
          {MIN_CANDLES_SLIDER_MAX}). Reduce indicator or filter periods.
        </p>
      ) : belowComputedMin ? (
        <p className="param-helper param-helper--warn">
          Must be at least {computedMinCandles} bars for this strategy&apos;s indicators and
          filters.
        </p>
      ) : outOfRange ? (
        <p className="param-helper param-helper--warn">
          Must be between {MIN_CANDLES_SLIDER_MIN} and {MIN_CANDLES_SLIDER_MAX} bars.
        </p>
      ) : (
        <p className="param-helper">
          Bars needed before the strategy can run on the next candle (
          {MIN_CANDLES_SLIDER_MIN}–{MIN_CANDLES_SLIDER_MAX}).
        </p>
      )}
      {minCandles > 0 ? (
        <p className="param-helper">
          About {formatCandleLookback(timeframe, minCandles)} at {TIMEFRAME_LABELS[timeframe]}.
        </p>
      ) : null}
    </ParameterCard>
  );
}
