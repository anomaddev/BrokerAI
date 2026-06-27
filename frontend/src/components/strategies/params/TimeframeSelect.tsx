import type { Timeframe } from "../../../lib/strategyParams";

type TimeframeOption = {
  value: Timeframe;
  label: string;
};

type TimeframeSelectProps = {
  id?: string;
  label?: string;
  required?: boolean;
  value: Timeframe;
  options: TimeframeOption[];
  onChange: (value: Timeframe) => void;
};

export default function TimeframeSelect({
  id = "strategy-timeframe",
  label,
  required = false,
  value,
  options,
  onChange,
}: TimeframeSelectProps) {
  return (
    <div className="param-control">
      {label ? (
        <label htmlFor={id} className="param-control-label">
          {label}
          {required ? <span className="param-control-required">Required</span> : null}
        </label>
      ) : null}
      <div className="research-select-wrap">
        <select
          id={id}
          className="research-select"
          value={value}
          aria-label={label ?? "Timeframe"}
          onChange={(event) => onChange(event.target.value as Timeframe)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
