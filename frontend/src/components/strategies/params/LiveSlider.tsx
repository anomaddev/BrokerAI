import type { ReactNode } from "react";
import NumberInput from "./NumberInput";

type LiveSliderProps = {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  suffix?: string;
  formatValue?: (value: number) => string;
  invalid?: boolean;
  readOnly?: boolean;
  /** Optional helper control shown next to the label. */
  labelHelp?: ReactNode;
  onChange: (value: number) => void;
};

export default function LiveSlider({
  id,
  label,
  value,
  min,
  max,
  step = 1,
  unit,
  suffix,
  formatValue,
  invalid,
  readOnly,
  labelHelp,
  onChange,
}: LiveSliderProps) {
  const display = formatValue
    ? `${formatValue(value)}${suffix ?? ""}`
    : `${value}${unit ? ` ${unit}` : ""}${suffix ?? ""}`;

  const labelNode = labelHelp ? (
    <div className="param-control-label-with-help">
      {readOnly ? (
        <span className="param-control-label">{label}</span>
      ) : (
        <label htmlFor={id} className="param-control-label">
          {label}
        </label>
      )}
      {labelHelp}
    </div>
  ) : readOnly ? (
    <span className="param-control-label">{label}</span>
  ) : (
    <label htmlFor={id} className="param-control-label">
      {label}
    </label>
  );

  if (readOnly) {
    return (
      <div className="param-control param-control--readonly">
        <div className="param-control-label-row">
          {labelNode}
          <span className="param-control-value">{display}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="param-control">
      <div className="param-control-label-row">
        {labelNode}
        <div className="param-control-value-row">
          <NumberInput
            id={id}
            value={value}
            min={min}
            max={max}
            step={step}
            unit={unit}
            suffix={suffix}
            formatValue={formatValue}
            invalid={invalid}
            inline
            onChange={onChange}
          />
        </div>
      </div>
      <input
        type="range"
        className="param-slider"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-valuenow={value}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-label={label}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
