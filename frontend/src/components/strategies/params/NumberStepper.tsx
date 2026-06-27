type NumberStepperProps = {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  invalid?: boolean;
  onChange: (value: number) => void;
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export default function NumberStepper({
  id,
  label,
  value,
  min,
  max,
  step = 1,
  invalid,
  onChange,
}: NumberStepperProps) {
  return (
    <div className="param-control">
      <label htmlFor={id} className="param-control-label">
        {label}
      </label>
      <div className={`param-stepper${invalid ? " param-stepper--invalid" : ""}`}>
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
    </div>
  );
}
