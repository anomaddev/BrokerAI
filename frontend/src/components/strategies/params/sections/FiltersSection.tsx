import ParameterCard from "../ParameterCard";
import ParamToggleRow from "../ParamToggleRow";
import ParamHelpTip from "../ParamHelpTip";
import NumberStepper from "../NumberStepper";
import LiveSlider from "../LiveSlider";
import { FILTER_CATALOG, findFilterCatalogEntry } from "../../../../lib/strategyParams";

export type AdxFilterState = {
  enabled: boolean;
  period: number;
  threshold: number;
};

export type AtrFilterState = {
  enabled: boolean;
  period: number;
  minAtr: number;
  minAtrJpy: number;
};

export type HtfBiasFilterState = {
  enabled: boolean;
  timeframe: "H1" | "H4";
};

type FiltersSectionProps = {
  expanded: boolean;
  onToggle: () => void;
  composable?: boolean;
  adx?: AdxFilterState;
  atr?: AtrFilterState;
  htfBias?: HtfBiasFilterState;
  onAdxChange?: (value: AdxFilterState) => void;
  onAtrChange?: (value: AtrFilterState) => void;
  onHtfBiasChange?: (value: HtfBiasFilterState) => void;
  onAddFilter?: (type: "adx" | "atr") => void;
  onRemoveFilter?: (type: "adx" | "atr") => void;
};

function filterHelpTip(type: "adx" | "atr") {
  const entry = findFilterCatalogEntry(type);
  if (!entry) return null;
  return <ParamHelpTip label={entry.label} title={entry.label} body={entry.description} />;
}

export default function FiltersSection({
  expanded,
  onToggle,
  composable = false,
  adx,
  atr,
  htfBias,
  onAdxChange,
  onAtrChange,
  onHtfBiasChange,
  onAddFilter,
  onRemoveFilter,
}: FiltersSectionProps) {
  const availableFilters = FILTER_CATALOG.filter((item) => {
    if (item.type === "adx") return !adx;
    if (item.type === "atr") return !atr;
    return false;
  });

  return (
    <ParameterCard
      className="parameter-card--filters"
      title="Trend & Volatility Filters"
      expanded={expanded}
      onToggle={onToggle}
    >
      {adx && onAdxChange && (
        <ParamToggleRow
          label="ADX filter"
          checked={adx.enabled}
          labelHelp={filterHelpTip("adx")}
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
          labelHelp={filterHelpTip("atr")}
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
            max={0.5}
            step={0.0001}
            formatValue={(v) => (v >= 0.01 ? v.toFixed(3) : v.toFixed(4))}
            onChange={(minAtr) => onAtrChange({ ...atr, minAtr })}
          />
          <p className="param-helper">
            Absolute ATR floor for non-JPY pairs (e.g. EUR/USD). Typical M15 values are around 0.0005–0.002.
          </p>
          <LiveSlider
            id="min-atr-jpy"
            label="Min ATR — JPY pairs"
            value={atr.minAtrJpy}
            min={0.0001}
            max={0.5}
            step={0.0001}
            formatValue={(v) => (v >= 0.01 ? v.toFixed(3) : v.toFixed(4))}
            onChange={(minAtrJpy) => onAtrChange({ ...atr, minAtrJpy })}
          />
          <p className="param-helper">
            Used when the pair quotes in JPY (e.g. USD/JPY). Typical M15 floors are around 0.05–0.10.
          </p>
          {composable && onRemoveFilter && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onRemoveFilter("atr")}>
              Remove ATR filter
            </button>
          )}
        </ParamToggleRow>
      )}

      {htfBias && onHtfBiasChange && (
        <ParamToggleRow
          label="Higher-timeframe bias"
          checked={htfBias.enabled}
          labelHelp={
            <ParamHelpTip
              label="Higher-timeframe bias"
              title="Higher-timeframe bias"
              body="Only allow entries aligned with the higher-timeframe EMA trend (fast above slow for longs, below for shorts). Uses closed HTF bars only — no look-ahead."
            />
          }
          onChange={(enabled) => onHtfBiasChange({ ...htfBias, enabled })}
        >
          <div className="param-control">
            <label className="param-control-label" htmlFor="htf-bias-tf">
              Bias timeframe
            </label>
            <div className="research-select-wrap">
              <select
                id="htf-bias-tf"
                className="research-select"
                value={htfBias.timeframe}
                onChange={(event) =>
                  onHtfBiasChange({
                    ...htfBias,
                    timeframe: event.target.value === "H1" ? "H1" : "H4",
                  })
                }
              >
                <option value="H1">H1</option>
                <option value="H4">H4</option>
              </select>
            </div>
          </div>
        </ParamToggleRow>
      )}

      {composable && availableFilters.length > 0 && onAddFilter && (
        <div className="param-control">
          <span className="param-control-label">Add filter</span>
          <div className="strategy-filter-add-list">
            {availableFilters.map((item) => (
              <div key={item.type} className="strategy-filter-add-row">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => onAddFilter(item.type)}
                >
                  {item.label}
                </button>
                <ParamHelpTip label={item.label} title={item.label} body={item.description} />
              </div>
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
