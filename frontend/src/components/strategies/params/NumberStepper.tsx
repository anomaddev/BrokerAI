import NumberInput from "./NumberInput";

type NumberStepperProps = {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  invalid?: boolean;
  readOnly?: boolean;
  /** Show +/- increment buttons. Defaults to false. */
  showButtons?: boolean;
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
  readOnly,
  showButtons = false,
  onChange,
}: NumberStepperProps) {
  if (readOnly || !showButtons) {
    return (
      <NumberInput
        id={id}
        label={label}
        value={value}
        min={min}
        max={max}
        step={step}
        invalid={invalid}
        readOnly={readOnly}
        onChange={onChange}
      />
    );
  }

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
        <NumberInput
          id={id}
          value={value}
          min={min}
          max={max}
          step={step}
          invalid={invalid}
          embedded
          onChange={onChange}
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
