import ParameterCard from "../ParameterCard";
import ParamToggleRow from "../ParamToggleRow";
import NumberStepper from "../NumberStepper";
import LiveSlider from "../LiveSlider";
import { FILTER_CATALOG } from "../../../../lib/strategyParams";

export type AdxFilterState = {
  enabled: boolean;
  period: number;
  threshold: number;
};

export type AtrFilterState = {
  enabled: boolean;
  period: number;
  minAtr: number;
};

type FiltersSectionProps = {
  expanded: boolean;
  onToggle: () => void;
  composable?: boolean;
  adx?: AdxFilterState;
  atr?: AtrFilterState;
  onAdxChange?: (value: AdxFilterState) => void;
  onAtrChange?: (value: AtrFilterState) => void;
  onAddFilter?: (type: "adx" | "atr") => void;
  onRemoveFilter?: (type: "adx" | "atr") => void;
};

export default function FiltersSection({
  expanded,
  onToggle,
  composable = false,
  adx,
  atr,
  onAdxChange,
  onAtrChange,
  onAddFilter,
  onRemoveFilter,
}: FiltersSectionProps) {
  const availableFilters = FILTER_CATALOG.filter((item) => {
    if (item.type === "adx") return !adx;
    if (item.type === "atr") return !atr;
    return false;
  });

  return (
    <ParameterCard title="Trend & Volatility Filters" expanded={expanded} onToggle={onToggle}>
      {adx && onAdxChange && (
        <ParamToggleRow
          label="ADX filter"
          checked={adx.enabled}
          onChange={(enabled) => onAdxChange({ ...adx, enabled })}
        >
          <NumberStepper
            id="adx-period"
            label="ADX period"
            value={adx.period}
            min={7}
            max={28}
            onChange={(period) => onAdxChange({ ...adx, period })}
          />
          <LiveSlider
            id="adx-threshold"
            label="ADX threshold"
            value={adx.threshold}
            min={15}
            max={40}
            onChange={(threshold) => onAdxChange({ ...adx, threshold })}
          />
          {composable && onRemoveFilter && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onRemoveFilter("adx")}>
              Remove ADX filter
            </button>
          )}
        </ParamToggleRow>
      )}

      {atr && onAtrChange && (
        <ParamToggleRow
          label="ATR filter"
          checked={atr.enabled}
          onChange={(enabled) => onAtrChange({ ...atr, enabled })}
        >
          <NumberStepper
            id="atr-period"
            label="ATR period"
            value={atr.period}
            min={7}
            max={28}
            onChange={(period) => onAtrChange({ ...atr, period })}
          />
          <LiveSlider
            id="min-atr"
            label="Min ATR value"
            value={atr.minAtr}
            min={0.0001}
            max={0.005}
            step={0.0001}
            formatValue={(v) => v.toFixed(4)}
            onChange={(minAtr) => onAtrChange({ ...atr, minAtr })}
          />
          {composable && onRemoveFilter && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onRemoveFilter("atr")}>
              Remove ATR filter
            </button>
          )}
        </ParamToggleRow>
      )}

      {composable && availableFilters.length > 0 && onAddFilter && (
        <div className="param-control">
          <span className="param-control-label">Add filter</span>
          <div className="confirm-actions">
            {availableFilters.map((item) => (
              <button
                key={item.type}
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => onAddFilter(item.type)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {composable && !adx && !atr && (
        <p className="param-helper">No filters added. Add ADX or ATR to filter entries.</p>
      )}
    </ParameterCard>
  );
}
