type LiveSliderProps = {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  formatValue?: (value: number) => string;
  showStepper?: boolean;
  invalid?: boolean;
  onChange: (value: number) => void;
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export default function LiveSlider({
  id,
  label,
  value,
  min,
  max,
  step = 1,
  unit,
  formatValue,
  showStepper,
  invalid,
  onChange,
}: LiveSliderProps) {
  const display = formatValue ? formatValue(value) : `${value}${unit ? ` ${unit}` : ""}`;

  return (
    <div className="param-control">
      <div className="param-control-label-row">
        <label htmlFor={id} className="param-control-label">
          {label}
        </label>
        <div className="param-control-value-row">
          {showStepper && (
            <div className={`param-stepper param-stepper--inline${invalid ? " param-stepper--invalid" : ""}`}>
              <button
                type="button"
                className="param-stepper-btn"
                aria-label={`Decrease ${label}`}
                onClick={() => onChange(clamp(value - step, min, max))}
              >
                −
              </button>
              <input
                id={id}
                type="number"
                className="param-stepper-input"
                min={min}
                max={max}
                step={step}
                value={value}
                onChange={(e) => {
                  const next = Number(e.target.value);
                  if (!Number.isNaN(next)) onChange(clamp(next, min, max));
                }}
              />
              <button
                type="button"
                className="param-stepper-btn"
                aria-label={`Increase ${label}`}
                onClick={() => onChange(clamp(value + step, min, max))}
              >
                +
              </button>
            </div>
          )}
          {!showStepper && <span className="param-control-value">{display}</span>}
        </div>
      </div>
      <input
        id={showStepper ? undefined : id}
        type="range"
        className="param-slider"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-valuenow={value}
        aria-valuemin={min}
        aria-valuemax={max}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={showStepper ? label : undefined}
      />
    </div>
  );
}
