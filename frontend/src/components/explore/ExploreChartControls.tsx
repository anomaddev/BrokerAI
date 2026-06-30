import ParamSelect from "../strategies/params/ParamSelect";
import TimeframeSelect from "../strategies/params/TimeframeSelect";
import {
  EXPLORE_TIMEFRAME_OPTIONS,
  HISTORY_DURATION_OPTIONS,
  type HistoryDuration,
} from "../../lib/exploreChartPresets";
import type { Timeframe } from "../../lib/strategyParams";

type ExploreChartControlsProps = {
  timeframe: Timeframe;
  historyDuration: HistoryDuration;
  onTimeframeChange: (value: Timeframe) => void;
  onHistoryChange: (value: HistoryDuration) => void;
};

export default function ExploreChartControls({
  timeframe,
  historyDuration,
  onTimeframeChange,
  onHistoryChange,
}: ExploreChartControlsProps) {
  return (
    <div className="explore-controls">
      <TimeframeSelect
        id="explore-candle-timeframe"
        label="Candle"
        value={timeframe}
        options={EXPLORE_TIMEFRAME_OPTIONS}
        onChange={onTimeframeChange}
      />
      <ParamSelect
        id="explore-history-duration"
        label="History"
        value={historyDuration}
        options={HISTORY_DURATION_OPTIONS}
        onChange={onHistoryChange}
      />
    </div>
  );
}
