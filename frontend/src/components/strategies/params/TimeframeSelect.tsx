import type { ReactNode } from "react";
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
  readOnly?: boolean;
  /** Optional helper control shown next to the label. */
  labelHelp?: ReactNode;
  onChange: (value: Timeframe) => void;
};

export default function TimeframeSelect({
  id = "strategy-timeframe",
  label,
  required = false,
  value,
  options,
  readOnly,
  labelHelp,
  onChange,
}: TimeframeSelectProps) {
  const selectedLabel = options.find((option) => option.value === value)?.label ?? value;
  const requiredBadge = required ? <span className="param-control-required">Required</span> : null;
  const labelInner = (
    <>
      {label}
      {requiredBadge}
    </>
  );
  const labelNode =
    label && labelHelp ? (
      <div className="param-control-label-with-help">
        {readOnly ? (
          <span className="param-control-label">{labelInner}</span>
        ) : (
          <label htmlFor={id} className="param-control-label">
            {labelInner}
          </label>
        )}
        {labelHelp}
      </div>
    ) : label ? (
      readOnly ? (
        <span className="param-control-label">{labelInner}</span>
      ) : (
        <label htmlFor={id} className="param-control-label">
          {labelInner}
        </label>
      )
    ) : null;

  if (readOnly) {
    return (
      <div className="param-control param-control--readonly">
        {labelNode}
        <span className="param-control-value param-control-value--locked">{selectedLabel}</span>
      </div>
    );
  }

  return (
    <div className="param-control">
      {labelNode}
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
